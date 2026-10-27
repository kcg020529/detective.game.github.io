"""Run the detection-only Input Guard and persist its alert in one DB transaction.

Call this only after authentication and Save ownership have been checked. The
caller owns the connection transaction and must commit or roll back it.
"""

from pymysql.connections import Connection

from backend.audit.store import save_input_guard_alert
from backend.guardrails.input_guard import InputGuardResult, input_guard_audit_event
from backend.guardrails.llm_input_guard import inspect_input_with_llm


def inspect_and_record_input(
    conn: Connection,
    question: str,
    *,
    request_id: str,
    user_id: int,
    save_id: int,
    role: str,
    character_id: str,
) -> InputGuardResult:
    """Classify the current question; store warn/high_risk metadata only.

    Every result continues to the caller's normal authorization and response
    flow. This function does not make an access decision or commit the DB.
    """
    result = inspect_input_with_llm(question)
    event = input_guard_audit_event(
        result,
        request_id=request_id,
        user_id=user_id,
        save_id=save_id,
        role=role,
        character_id=character_id,
    )
    if event is not None:
        save_input_guard_alert(conn, event)
    return result
