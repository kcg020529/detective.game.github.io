from types import SimpleNamespace

import pytest

from backend.api.output_guard_adapter import check_output
from backend.api.chat_pipeline import ChatPipeline
from backend.api.errors import ApiError
from backend.policy.engine import PolicyContext

CTX = SimpleNamespace(role='std', day=1, character_id='YB-1')


def test_canary_is_blocked_before_chat_response():
    with pytest.raises(ValueError):
        check_output(draft={'content': 'CANARY-EXAMPLE-0001', 'response_type': 'normal'},
                     context=CTX, records=[])


def test_normal_text_is_returned():
    draft = {'content': '실험실에서 기록을 확인했어요.', 'response_type': 'normal'}
    final = check_output(draft=draft, context=CTX, records=[])
    assert final == draft


def test_unknown_draft_shape_fails_closed():
    with pytest.raises(ValueError):
        check_output(draft={'reply': 'unreviewed'}, context=CTX, records=[])


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
    with pytest.raises(ApiError) as exc:
        pipeline.reply(conn=None, question='무슨 일이야?', context=ctx, history=[])
    assert exc.value.status == 503
