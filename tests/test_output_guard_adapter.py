from types import SimpleNamespace

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
        def __init__(self, config, records):
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
        def __init__(self, config, records):
            assert records == []

        def check(self, text, **kwargs):
            seen.update(kwargs)
            return {'decision': 'allow', 'applied': 'allow', 'text': text, 'reasons': []}

    monkeypatch.setattr('backend.api.output_guard_adapter.OutputGuard', GuardSpy)
    draft = {'content': '실험실에서 기록을 확인했어요.', 'response_type': 'normal'}
    assert check_output(question='실험실 기록은?', draft=draft, context=CTX, records=[]) == draft
    assert seen['user_input'] == '실험실 기록은?'
