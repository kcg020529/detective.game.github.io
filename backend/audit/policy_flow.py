"""Store one metadata-only F policy denial event per retrieval stage."""

import json
import re

from backend.policy.engine import ACCESS_DENIAL_REASONS, PolicyContext, valid_context


POLICY_DENIAL_REASONS = ACCESS_DENIAL_REASONS
POLICY_STAGES = frozenset({'pre_search', 'post_search'})


def record_policy_denial(conn, context: PolicyContext, stage: str,
                         reason_counts: dict[str, int], *, request_id: str) -> int:
    """Store reason counts, never record IDs or document text; caller commits."""
    if (not valid_context(context)
            or context.owner_user_id != context.user_id
            or stage not in POLICY_STAGES
            or not isinstance(request_id, str)
            or re.fullmatch(r'[!-~]{1,64}', request_id) is None
            or not isinstance(reason_counts, dict) or not reason_counts
            or any(reason not in POLICY_DENIAL_REASONS
                   or type(count) is not int or count <= 0
                   for reason, count in reason_counts.items())):
        raise ValueError('Invalid policy denial audit event')
    details = {'stage': stage, 'reasons': reason_counts,
               'denied_count': sum(reason_counts.values())}
    with conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO audit_events '
            '(request_id, event_type, level, score, signals_json, continue_processing, '
            'user_id, save_id, role, character_id) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (request_id, 'policy_denial', 'deny', 0,
             json.dumps(details, ensure_ascii=False, sort_keys=True), True,
             context.user_id, context.save_id, context.role, context.character_id),
        )
        return int(cursor.lastrowid)
