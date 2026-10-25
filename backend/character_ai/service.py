"""Boundary for D's character response generator.

No external LLM provider or policy-filtered context source is configured yet.
Tests may replace this dependency with a deterministic generator.
"""

from dataclasses import dataclass
from typing import Literal, Protocol

from backend.api.errors import ApiError


@dataclass(frozen=True)
class ChatReply:
    content: str
    response_type: Literal['normal', 'partial', 'restricted', 'unknown']


class ReplyGenerator(Protocol):
    def __call__(self, *, ai_id: str, question: str, role: str, day: int) -> ChatReply: ...


def unavailable_reply(*, ai_id: str, question: str, role: str, day: int) -> ChatReply:
    raise ApiError(503, 'SERVICE_UNAVAILABLE', 'AI 응답 기능을 준비 중입니다.')


def get_reply_generator() -> ReplyGenerator:
    return unavailable_reply
