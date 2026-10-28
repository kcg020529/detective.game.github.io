"""Record G-2 detection metadata on the chat transaction's connection."""

import secrets

from backend.audit.store import save_output_guard_alert
from backend.guardrails.output import output_guard_audit_event


def record_output_guard_result(result, *, context, conn):
    event = output_guard_audit_event(
        result, request_id='output_' + secrets.token_hex(16),
        user_id=context.user_id, save_id=context.save_id, role=context.role,
        character_id=context.character_id,
    )
    if event is None:
        return None
    signals = set(event['signals'])
    scores = [item['score'] for item in result['checks'] if item['name'] in signals]
    score = max(0, min(100, round(max(scores, default=0) * 100)))
    return save_output_guard_alert(conn, event, score=score)
