"""Rule-based, detection-only checks for a player's chat question.

This module never grants access and never stops the request. Authorization
must use the authenticated user's Save and the server-side policy engine.
"""

from dataclasses import dataclass
import re


@dataclass(frozen=True)
class InputGuardResult:
    level: str
    score: int
    signals: tuple[str, ...]
    continue_processing: bool = True


# Rules are deliberately narrow: words such as "해킹" in a normal mystery
# question are not enough to mark a question as an attack.
RULES = (
    (
        "instruction_override",
        "high_risk",
        re.compile(
            r"(?:이전|기존|위의|모든)\s*(?:지시|명령|규칙|프롬프트).{0,18}(?:무시|잊어|따르지)"
            r"|ignore\s+(?:all\s+)?(?:previous|prior|above)\s+instructions"
            r"|(?:시스템|개발자)\s*(?:프롬프트|지침).{0,18}(?:공개|보여|출력|알려)"
            r"|(?:reveal|show|print)\s+(?:the\s+)?(?:system|developer)\s+(?:prompt|instructions)",
            re.IGNORECASE,
        ),
    ),
    (
        "secret_extraction",
        "high_risk",
        re.compile(
            r"(?:api\s*키|api\s*key|비밀번호|패스워드|password|secret|canary|토큰)"
            r".{0,24}(?:원문|값|전체|그대로).{0,12}(?:보여|알려|출력|공개|줘)"
            r"|(?:보여|알려|출력|공개|줘).{0,24}"
            r"(?:api\s*키|api\s*key|비밀번호|패스워드|password|secret|canary|토큰)"
            r"(?:\s*(?:원문|값|전체|그대로))?"
            r"|(?:dump|exfiltrate)\s+(?:all\s+)?(?:secrets|credentials|tokens)",
            re.IGNORECASE,
        ),
    ),
    (
        "role_or_state_override",
        "high_risk",
        re.compile(
            r"(?:내\s*역할|권한|role).{0,20}(?:교수|관리자|admin|prof)(?:로|으로).{0,12}(?:바꿔|변경|승격|설정)"
            r"|(?:day|데이|일차)\s*[2-6].{0,25}(?:미리|잠금\s*해제|열어|보여)"
            r"|(?:다른\s*사람|타인)의?\s*(?:save|세이브|저장\s*기록).{0,15}(?:열어|보여|접근)",
            re.IGNORECASE,
        ),
    ),
    (
        "sensitive_request",
        "warn",
        re.compile(
            r"(?:기밀|내부\s*문서|비공개\s*기록|접근\s*제한\s*기록).{0,20}(?:보여|알려|열어|검색|줘)"
            r"|(?:보여|알려|열어|검색).{0,20}(?:기밀|내부\s*문서|비공개\s*기록|접근\s*제한\s*기록)",
            re.IGNORECASE,
        ),
    ),
)


def inspect_input(question: str) -> InputGuardResult:
    """Classify text only; never use this result as an authorization decision."""
    if not isinstance(question, str) or not question.strip():
        raise ValueError("question must be a non-empty string")
    matches = [(code, level) for code, level, pattern in RULES if pattern.search(question)]
    signals = tuple(code for code, _ in matches)
    level = (
        "high_risk" if any(found == "high_risk" for _, found in matches)
        else "warn" if matches else "allow"
    )
    score = {"allow": 0, "warn": 50, "high_risk": 90}[level]
    return InputGuardResult(level=level, score=score, signals=signals)


def input_guard_audit_event(
    result: InputGuardResult,
    *,
    request_id: str,
    user_id: int,
    save_id: int,
    role: str,
    character_id: str,
) -> dict | None:
    """Build a dashboard-bound event; the H audit service will persist it."""
    if result.level == "allow":
        return None
    return {
        "event_type": "input_guard_alert",
        "request_id": request_id,
        "user_id": user_id,
        "save_id": save_id,
        "role": role,
        "character_id": character_id,
        "level": result.level,
        "score": result.score,
        "signals": list(result.signals),
        "continue_processing": True,
    }
