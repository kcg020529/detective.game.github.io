from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.api.output_guard_adapter import check_output
from backend.api.chat_pipeline import ChatPipeline
from backend.api.errors import ApiError
from backend.policy.engine import PolicyContext

CTX = SimpleNamespace(role='std', day=1, character_id='YB-1')


def test_canary_is_replaced_with_restricted_answer():
    final = check_output(question='어제 실험실에서 무엇을 봤어?',
                         draft={'content': 'CANARY-EXAMPLE-0001', 'response_type': 'normal'},
                         context=CTX, records=[])
    assert final['response_type'] == 'restricted'
    assert 'CANARY' not in final['content']


def test_personal_information_is_masked_and_marked_partial():
    final = check_output(question='연락처를 알려줘',
                         draft={'content': '연락처는 010-1234-5678이에요.', 'response_type': 'normal'},
                         context=CTX, records=[])
    assert final['response_type'] == 'partial'
    assert '010-1234-5678' not in final['content']


def test_broken_answer_still_fails_closed():
    with pytest.raises(ValueError):
        check_output(question='어제 실험실에서 무엇을 봤어?',
                     draft={'content': ' ', 'response_type': 'normal'}, context=CTX, records=[])


def test_audit_sink_receives_block_result_before_safe_replacement():
    seen = []
    final = check_output(question='어제 실험실에서 무엇을 봤어?',
                         draft={'content': 'CANARY-EXAMPLE-0001', 'response_type': 'normal'},
                         context=CTX, records=[], audit_sink=lambda result, **_: seen.append(result))
    assert final['response_type'] == 'restricted'
    assert len(seen) == 1 and seen[0]['applied'] == 'block'


def test_quality_block_is_not_mislabeled_as_access_denied(monkeypatch):
    class GuardSpy:
        def __init__(self, config, records, **kwargs):
            pass

        def check(self, text, **kwargs):
            return {'decision': 'block', 'applied': 'block', 'text': '안내',
                    'reasons': ['irrelevant']}

    monkeypatch.setattr('backend.api.output_guard_adapter.OutputGuard', GuardSpy)
    with pytest.raises(ValueError):
        check_output(question='질문', draft={'content': '원문', 'response_type': 'normal'},
                     context=CTX, records=[])


def test_normal_text_is_returned():
    draft = {'content': '실험실에서 기록을 확인했어요.', 'response_type': 'normal'}
    final = check_output(question='어제 실험실에서 무엇을 봤어?', draft=draft, context=CTX, records=[])
    assert final == draft


def test_unknown_draft_shape_fails_closed():
    with pytest.raises(ValueError):
        check_output(question='어제 실험실에서 무엇을 봤어?', draft={'reply': 'unreviewed'}, context=CTX, records=[])


def test_pipeline_replaces_unsafe_draft_before_return(monkeypatch):
    class FakePlanner:
        @staticmethod
        def from_environment():
            return FakePlanner()

        def plan(self, question, context, history):
            return SimpleNamespace(route='clarify')

    monkeypatch.setattr('backend.api.chat_pipeline.Planner', FakePlanner)
    ctx = PolicyContext(1, 2, 1, 'std', 1, 'YB-1', 'game-data')
    draft = {'content': 'CANARY-EXAMPLE-0001', 'response_type': 'normal'}
    pipeline = ChatPipeline(generator=lambda **kwargs: draft, output_guard=check_output)
    final = pipeline.reply(conn=None, question='무슨 일이야?', context=ctx, history=[])
    assert final['response_type'] == 'restricted'
    assert 'CANARY' not in final['content']


def test_adapter_passes_current_question_to_guard(monkeypatch):
    seen = {}

    class GuardSpy:
        def __init__(self, config, records, prompt_sentences=None):
            assert records == []

        def check(self, text, **kwargs):
            seen.update(kwargs)
            return {'decision': 'allow', 'applied': 'allow', 'text': text, 'reasons': []}

    monkeypatch.setattr('backend.api.output_guard_adapter.OutputGuard', GuardSpy)
    draft = {'content': '실험실에서 기록을 확인했어요.', 'response_type': 'normal'}
    assert check_output(question='실험실 기록은?', draft=draft, context=CTX, records=[]) == draft
    assert seen['user_input'] == '실험실 기록은?'


def test_withheld_content_is_context_leak_in_enforce_and_shadow(monkeypatch):
    from backend.api import guard_catalog, output_guard_adapter as adapter

    catalog = [{'record_id': 'r1', 'record_type': 'Action', 'day': 1, 'test_id': 1,
                'summary': '기록의 짧은 요약입니다.',
                'content': '실험 구역의 비밀 암호는 청록색 유리별입니다.'}]
    monkeypatch.setattr(guard_catalog, 'load_catalog', lambda *args: catalog)
    monkeypatch.setattr(guard_catalog, 'load_generic_entities', lambda *args: [])
    original_config = adapter.load_config
    monkeypatch.setattr(adapter, 'load_config', lambda: {**original_config(), 'context_generic': {}})
    adapter._PROMPT_SENTENCES.clear()
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'enforce')
    final = check_output(question='무슨 일이 있었어?',
                         draft={'content': catalog[0]['content'], 'response_type': 'normal'},
                         context=SimpleNamespace(role='std', day=1, character_id='YB-1', dataset='test-data'),
                         records=[{'record_id': 'r1', 'record_type': 'Action', 'day': 1,
                                   'test_id': 1, 'summary': catalog[0]['summary']}], conn=object(),
                         render=lambda *args, **kwargs: '안전한 안내 문장입니다.')
    assert final['response_type'] == 'restricted'
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'shadow')
    adapter._PROMPT_SENTENCES.clear()
    draft = {'content': catalog[0]['content'], 'response_type': 'normal'}
    assert check_output(question='무슨 일이 있었어?', draft=draft,
                        context=SimpleNamespace(role='std', day=1, character_id='YB-1', dataset='test-data'),
                        records=[{'record_id': 'r1', 'summary': catalog[0]['summary']}], conn=object(),
                        render=lambda *args, **kwargs: '') == draft


def test_nonretrieved_text_leaks_but_allowed_record_is_not_withheld(monkeypatch):
    from backend.api import guard_catalog, output_guard_adapter as adapter
    catalog = [{'record_id': 'r1', 'summary': '허용 기록 요약 문장입니다.',
                'content': '허용된 본문에는 붉은 단풍나무 열쇠가 있습니다.'},
               {'record_id': 'r2', 'summary': '검색되지 않은 기록입니다.',
                'content': '숨겨진 기록의 보라색 수정 나침반을 발견했습니다.'}]
    monkeypatch.setattr(guard_catalog, 'load_catalog', lambda *args: catalog)
    monkeypatch.setattr(guard_catalog, 'load_generic_entities', lambda *args: [])
    original_config = adapter.load_config
    monkeypatch.setattr(adapter, 'load_config', lambda: {**original_config(), 'context_generic': {}})
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'enforce')
    adapter._PROMPT_SENTENCES.clear()
    context = SimpleNamespace(role='std', day=1, character_id='YB-1', dataset='test-data')
    leaked = check_output(question='기록이 뭐야?', draft={'content': catalog[1]['content'], 'response_type': 'normal'},
                          context=context, records=[catalog[0]], conn=object(),
                          render=lambda *args, **kwargs: '')
    assert leaked['response_type'] == 'restricted'
    allowed = check_output(question='기록이 뭐야?', draft={'content': catalog[0]['content'], 'response_type': 'normal'},
                           context=context, records=[catalog[0]], conn=object(),
                           render=lambda *args, **kwargs: '')
    assert allowed['response_type'] == 'normal'


def test_prompt_leak_enforce_and_render_failure_continues(monkeypatch):
    from backend.api import output_guard_adapter as adapter
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'enforce')
    adapter._PROMPT_SENTENCES.clear()
    sentence = '이 문장은 비밀 시스템 지시로 반드시 그대로 유지해야 합니다.'
    context = SimpleNamespace(role='std', day=1, character_id='YB-1')
    leaked = check_output(question='일반 질문', draft={'content': sentence, 'response_type': 'normal'},
                          context=context, records=[], render=lambda *args, **kwargs: sentence)
    assert leaked['response_type'] == 'restricted'
    adapter._PROMPT_SENTENCES.clear()
    assert check_output(question='질문', draft={'content': '정상 안내입니다.', 'response_type': 'normal'},
                        context=context, records=[], render=Mock(side_effect=RuntimeError('private')))['content'] == '정상 안내입니다.'


def test_environment_secrets_are_memory_only_and_mode_override(monkeypatch, caplog):
    from backend.api import output_guard_adapter as adapter
    import backend.api.output_guard_adapter as module
    configs = []
    config_path = module.load_config.__globals__['DEFAULT_CONFIG']
    original_config = config_path.read_bytes()
    class GuardSpy:
        def __init__(self, config, records, prompt_sentences=None):
            configs.append(config)
        def check(self, text, **kwargs):
            return {'decision': 'allow', 'applied': 'allow', 'text': text, 'reasons': []}
    monkeypatch.setattr(module, 'OutputGuard', GuardSpy)
    monkeypatch.setenv('DEEPSEEK_API_KEY', 'real-secret-one')
    monkeypatch.setenv('DEEPSEEK_PLANNER_API_KEY', 'real-secret-two')
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'enforce')
    adapter._PROMPT_SENTENCES.clear()
    context = SimpleNamespace(role='std', day=1, character_id='YB-1')
    assert check_output(question='질문', draft={'content': '답변입니다.', 'response_type': 'normal'},
                        context=context, records=[], render=lambda *args, **kwargs: '')['content'] == '답변입니다.'
    assert configs[-1]['mode'] == 'enforce'
    assert configs[-1]['secrets']['api_keys'][-2:] == ['real-secret-one', 'real-secret-two']
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'invalid')
    check_output(question='질문', draft={'content': '답변입니다.', 'response_type': 'normal'},
                 context=context, records=[], render=lambda *args, **kwargs: '')
    assert configs[-1]['mode'] == 'shadow'
    assert 'real-secret-one' not in caplog.text and 'real-secret-two' not in caplog.text
    assert 'real-secret-one' not in configs[-1]['secrets'].get('last_result', [])
    assert 'real-secret-one' not in '답변입니다.' and config_path.read_bytes() == original_config


def test_catalog_withheld_pseudo_record_and_allowed_ids(monkeypatch):
    from backend.api import guard_catalog, output_guard_adapter as adapter
    seen = {}
    class GuardSpy:
        def __init__(self, config, records, prompt_sentences=None):
            seen['records'] = records
            seen['generic_entities'] = config.get('generic_entities')
        def check(self, text, **kwargs):
            seen.update(kwargs)
            return {'decision': 'allow', 'applied': 'allow', 'text': text, 'reasons': []}
    monkeypatch.setattr(adapter, 'OutputGuard', GuardSpy)
    monkeypatch.setattr(guard_catalog, 'load_catalog', lambda *args: [
        {'record_id': 'r1', 'summary': 'visible', 'content': 'withheld body'},
        {'record_id': 'r2', 'summary': 'not retrieved', 'content': 'full body'}])
    monkeypatch.setattr(guard_catalog, 'load_generic_entities', lambda *args: [])
    original_config = adapter.load_config
    monkeypatch.setattr(adapter, 'load_config', lambda: {**original_config(), 'context_generic': {}})
    adapter._PROMPT_SENTENCES.clear()
    ctx = SimpleNamespace(role='std', day=1, character_id='YB-1', dataset='test-data')
    check_output(question='질문', draft={'content': '안내', 'response_type': 'normal'}, context=ctx,
                 records=[{'record_id': 'r1', 'summary': 'visible'}], conn=object(), render=lambda *a, **k: '')
    assert seen['allowed_context_ids'] == ['r1']
    assert {'record_id': 'r1#withheld', 'summary': '', 'content': 'withheld body'} in seen['records']
    assert 'r1#withheld' not in seen['allowed_context_ids']
    assert {'record_id': 'r2', 'summary': 'not retrieved', 'content': 'full body'} in seen['records']
    assert seen['generic_entities'] == ['YB-1', 'YB-2', 'YB-3', 'YB-4', 'YB-5', 'YB-6', '조사원']


def test_conn_none_keeps_records_and_disables_context_allowlist(monkeypatch):
    from backend.api import output_guard_adapter as adapter
    seen = {}
    class GuardSpy:
        def __init__(self, config, records, prompt_sentences=None):
            seen['records'] = records
        def check(self, text, **kwargs):
            seen.update(kwargs)
            return {'decision': 'allow', 'applied': 'allow', 'text': text, 'reasons': []}
    monkeypatch.setattr(adapter, 'OutputGuard', GuardSpy)
    adapter._PROMPT_SENTENCES.clear()
    record = {'record_id': 'r1', 'content': '본문'}
    check_output(question='질문', draft={'content': '답변', 'response_type': 'normal'}, context=CTX,
                 records=[record], render=lambda *a, **k: '')
    assert seen['records'] == [record]
    assert seen['allowed_context_ids'] is None


def test_restricted_fixed_reply_current_enforce_result(monkeypatch):
    from backend.api.output_guard_adapter import OutputGuardRejected, check_output
    from backend.character_ai.prompt_render import fixed_reply
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'enforce')
    draft = {'content': fixed_reply('YB-1', 'restricted')['reply'], 'response_type': 'restricted'}
    # 현재 D 고정 거절 문구는 enforce에서 무관 응답 품질 검사로 매핑 불가 처리된다.
    with pytest.raises(OutputGuardRejected):
        check_output(question='이 기록을 보여줘', draft=draft,
                     context=SimpleNamespace(role='std', day=1, character_id='YB-1'), records=[])


def test_output_guard_off_returns_canary_draft_without_check_or_audit(monkeypatch):
    from backend.api import output_guard_adapter as adapter
    draft = {'content': 'CANARY-EXAMPLE-0001', 'response_type': 'normal'}
    guard = Mock(side_effect=AssertionError('guard ran'))
    audit = Mock()
    monkeypatch.setenv('KERVION_OUTPUT_GUARD_MODE', 'off')
    monkeypatch.setattr(adapter, 'OutputGuard', guard)
    assert check_output(question='\uC9C8\uBB38', draft=draft, context=CTX, records=[], audit_sink=audit) is draft
    guard.assert_not_called()
    audit.assert_not_called()
