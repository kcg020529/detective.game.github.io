import logging
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.api.character_adapter import make_generator
from backend.rag.service import Retrieval


@pytest.fixture
def setup():
    chat = Mock(return_value={'data': {'reply': 'answer secret', 'used': ['m1', 'real-id', 'm99']}})
    render = Mock(return_value='prompt secret')
    fixed = Mock(return_value={'reply': 'fixed reply', 'used': []})
    return make_generator(chat, render, fixed), chat, render, fixed


def call(generator, route, retrieval=None, records=None, history=None, code=None):
    return generator(question='question secret', context=SimpleNamespace(character_id='YB-2'),
                     history=history or [], plan=SimpleNamespace(route=route, clarification_code=code),
                     records=records or [], retrieval=retrieval)


def test_answer_memory_history_used_and_logging(setup, caplog):
    generator, chat, render, _ = setup
    retrieval = Retrieval([{'record_id': 'real-id'}], [{'id': 'm1', 'text': 'memory secret'}],
                          'ok', {'m1': 'real-id'})
    history = [{'sender': 'user' if i % 2 == 0 else 'ai', 'content': str(i)} for i in range(8)]
    with caplog.at_level(logging.DEBUG, logger='backend.api.character_adapter'):
        result = call(generator, 'retrieve', retrieval, history=history)
    assert result == {'content': 'answer secret', 'response_type': 'normal'}
    assert render.call_args.args == ('YB-2', 'answer')
    assert render.call_args.kwargs['memory'] == retrieval.memory
    assert render.call_args.kwargs['history'] == []
    assert 'used=1 dropped=2' in caplog.text
    assert all(secret not in caplog.text for secret in ('answer secret', 'prompt secret', 'question secret', 'real-id', 'memory secret'))
    chat.assert_called_once_with('prompt secret', 'question secret')


@pytest.mark.parametrize('route,retrieval,mode,response', [
    ('character', None, 'answer', 'normal'),
    ('retrieve', Retrieval([], [], 'no_match', {}), 'unknown', 'unknown'),
])
def test_llm_routes(setup, route, retrieval, mode, response):
    generator, _, render, _ = setup
    result = call(generator, route, retrieval)
    assert result == {'content': 'answer secret', 'response_type': response}
    assert render.call_args.args == ('YB-2', mode)
    assert render.call_args.kwargs['memory'] == []


def test_restricted_and_off_topic_do_not_call_llm(setup):
    generator, chat, render, fixed = setup
    assert call(generator, 'retrieve', Retrieval([], [], 'no_allowed_records', {})) == {
        'content': 'fixed reply', 'response_type': 'restricted'}
    fixed.assert_called_with('YB-2', 'restricted')
    assert call(generator, 'out_of_scope') == {'content': 'fixed reply', 'response_type': 'unknown'}
    fixed.assert_called_with('YB-2', 'off_topic')
    chat.assert_not_called()
    render.assert_not_called()


@pytest.mark.parametrize('code,text', [
    ('AMBIGUOUS_REFERENCE', '어떤 인물이나 회차를 말씀하시는 건가요?'),
    ('INSUFFICIENT_CONTEXT', '조금 더 구체적으로 알려 주실 수 있나요?'),
])
def test_clarify(setup, code, text):
    generator, chat, render, fixed = setup
    assert call(generator, 'clarify', code=code) == {'content': text, 'response_type': 'unknown'}
    chat.assert_not_called()
    render.assert_not_called()
    fixed.assert_not_called()


def test_fallback_builds_memory_and_empty_result_is_unknown(setup):
    generator, _, render, _ = setup
    assert call(generator, 'retrieve', records=[{'record_id': 'real-id', 'summary': 'memory'}])['response_type'] == 'normal'
    assert render.call_args.kwargs['memory'] == [{'id': 'm1', 'text': 'memory'}]
    assert call(generator, 'retrieve')['response_type'] == 'unknown'
    assert render.call_args.kwargs['memory'] == []


def test_blank_reply_raises(setup):
    generator, chat, _, _ = setup
    chat.return_value = {'data': {'reply': '  ', 'used': []}}
    with pytest.raises(ValueError):
        call(generator, 'character')
