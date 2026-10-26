"""Persist Input Guard alert metadata inside the caller's DB transaction."""

import json
import re

from pymysql.connections import Connection

from backend.guardrails.input_guard import MODEL_SIGNAL_LEVELS, RULES


SIGNAL_LEVELS = {**{code: rule_level for code, rule_level, _ in RULES}, **MODEL_SIGNAL_LEVELS}
LEVEL_SCORES = {'warn': 50, 'high_risk': 90}
EVENT_KEYS = frozenset({
    'event_type', 'request_id', 'user_id', 'save_id', 'role',
    'character_id', 'level', 'score', 'signals', 'continue_processing',
})


def save_input_guard_alert(conn: Connection, event: dict) -> int:
    """Store a validated alert; caller commits or rolls back the transaction."""
    if set(event) != EVENT_KEYS:
        raise ValueError('Input Guard event fields do not match the audit contract')
    level = event['level']
    signals = event['signals']
    if (event['event_type'] != 'input_guard_alert'
            or level not in LEVEL_SCORES
            or event['score'] != LEVEL_SCORES[level]
            or event['continue_processing'] is not True
            or not isinstance(signals, list)
            or not signals
            or any(not isinstance(signal, str) or signal not in SIGNAL_LEVELS for signal in signals)
            or ('high_risk' if any(SIGNAL_LEVELS[signal] == 'high_risk' for signal in signals)
                else 'warn') != level
            or not isinstance(event['request_id'], str)
            or re.fullmatch(r'[!-~]{1,64}', event['request_id']) is None
            or not isinstance(event['user_id'], int) or event['user_id'] <= 0
            or not isinstance(event['save_id'], int) or event['save_id'] <= 0
            or event['role'] not in ('prof', 'grad', 'std')
            or event['character_id'] not in {f'YB-{i}' for i in range(1, 7)}):
        raise ValueError('Invalid Input Guard audit event')

    with conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO audit_events '
            '(request_id, event_type, level, score, signals_json, continue_processing, '
            'user_id, save_id, role, character_id) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (
                event['request_id'], event['event_type'], level, event['score'],
                json.dumps(signals, ensure_ascii=False), True,
                event['user_id'], event['save_id'], event['role'], event['character_id'],
            ),
        )
        return int(cursor.lastrowid)
