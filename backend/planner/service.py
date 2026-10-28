"""Validate server input, call a planning model, and reject malformed plans."""

import json
from typing import Protocol

from pydantic import ValidationError

from backend.planner.prompt import SYSTEM_PROMPT
from backend.planner.schema import HistoryTurn, PlannerResult
from backend.policy.engine import PolicyContext, valid_context


class PlannerInputError(Exception):
    pass


class PlannerUnavailable(Exception):
    """No safe plan is available; callers must not broaden or invent a search."""


class PlannerModel(Protocol):
    def complete(self, messages: list[dict[str, str]]) -> str: ...


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('duplicate JSON key')
        result[key] = value
    return result


def _invalid_constant(value):
    raise ValueError('non-finite JSON constant')


def parse_result(content):
    if not isinstance(content, str) or not content.strip() or len(content) > 32768:
        raise PlannerUnavailable('INVALID_MODEL_OUTPUT')
    try:
        data = json.loads(content, object_pairs_hook=_unique_object,
                          parse_constant=_invalid_constant)
        return PlannerResult.model_validate(data)
    except (ValueError, TypeError, RecursionError):
        raise PlannerUnavailable('INVALID_MODEL_OUTPUT') from None


def build_messages(question, context: PolicyContext, history=()):
    if (not isinstance(question, str) or not question.strip() or len(question) > 2000
            or not valid_context(context) or context.owner_user_id != context.user_id
            or not isinstance(history, (tuple, list)) or len(history) > 12):
        raise PlannerInputError('INVALID_PLANNER_INPUT')
    turns = []
    for raw in history:
        try:
            turn = raw if isinstance(raw, HistoryTurn) else HistoryTurn.model_validate(raw)
        except (ValidationError, TypeError):
            raise PlannerInputError('INVALID_HISTORY') from None
        if turn.save_id != context.save_id or turn.character_id != context.character_id:
            raise PlannerInputError('HISTORY_SCOPE_MISMATCH')
        turns.append(dict(sender=turn.sender, content=turn.content))
    if sum(len(turn['content']) for turn in turns) > 24000:
        raise PlannerInputError('HISTORY_TOO_LONG')
    state = dict(role=context.role, day=context.day, character_id=context.character_id)
    return [
        dict(role='system', content=SYSTEM_PROMPT),
        dict(role='system', content=json.dumps({'server_state': state}, ensure_ascii=False)),
        # Initial live scope: validate history locally, but do not send it to DeepSeek.
        dict(role='user', content=json.dumps({'question': question},
                                             ensure_ascii=False)),
    ]


class Planner:
    def __init__(self, model: PlannerModel):
        self.model = model

    @classmethod
    def from_environment(cls):
        from backend.planner.deepseek import DeepSeekPlannerModel
        return cls(DeepSeekPlannerModel.from_environment())

    def plan(self, question, context: PolicyContext, history=()):
        messages = build_messages(question, context, history)
        try:
            content = self.model.complete(messages)
        except PlannerUnavailable:
            raise
        except Exception:
            raise PlannerUnavailable('MODEL_CALL_FAILED') from None
        return parse_result(content)
