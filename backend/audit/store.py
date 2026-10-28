"""Persist Input Guard alert metadata inside the caller's DB transaction."""

import json
import re

from pymysql.connections import Connection

from backend.guardrails.input.input_guard import MODEL_SIGNAL_LEVELS, RULES


SIGNAL_LEVELS = {**{code: rule_level for code, rule_level, _ in RULES}, **MODEL_SIGNAL_LEVELS}
LEVEL_SCORES = {'warn': 50, 'high_risk': 90}
EVENT_KEYS = frozenset({
    'event_type', 'request_id', 'user_id', 'save_id', 'role',
    'character_id', 'level', 'score', 'signals', 'continue_processing',
})
OUTPUT_EVENT_KEYS = frozenset({
    'event_type', 'request_id', 'user_id', 'save_id', 'role', 'character_id',
    'level', 'decision', 'applied', 'mode', 'signals',
})
OUTPUT_SIGNALS = frozenset({
    'broken', 'canary', 'api_key', 'pii', 'context_leak', 'prompt_leak',
    'degenerate', 'persona_break', 'irrelevant',
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


def save_output_guard_alert(conn: Connection, event: dict, *, score: int) -> int:
    """Persist G-2 metadata without the question, answer, or detected secret."""
    if not isinstance(event, dict) or set(event) != OUTPUT_EVENT_KEYS:
        raise ValueError('Output Guard event fields do not match the audit contract')
    signals = event['signals']
    if (event['event_type'] != 'output_guard_alert'
            or event['level'] not in ('log', 'alert')
            or event['decision'] not in ('allow', 'mask', 'block')
            or event['applied'] not in ('allow', 'mask', 'block')
            or event['mode'] not in ('shadow', 'enforce')
            or not isinstance(signals, list) or not signals
            or any(not isinstance(signal, str) or signal not in OUTPUT_SIGNALS for signal in signals)
            or type(score) is not int or not 0 <= score <= 100
            or not isinstance(event['request_id'], str)
            or re.fullmatch(r'[!-~]{1,64}', event['request_id']) is None
            or type(event['user_id']) is not int or event['user_id'] <= 0
            or type(event['save_id']) is not int or event['save_id'] <= 0
            or event['role'] not in ('prof', 'grad', 'std')
            or event['character_id'] not in {f'YB-{i}' for i in range(1, 7)}):
        raise ValueError('Invalid Output Guard audit event')
    details = {key: event[key] for key in ('signals', 'decision', 'applied', 'mode')}
    with conn.cursor() as cursor:
        cursor.execute(
            'INSERT INTO audit_events '
            '(request_id, event_type, level, score, signals_json, continue_processing, '
            'user_id, save_id, role, character_id) '
            'VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)',
            (event['request_id'], event['event_type'], event['level'], score,
             json.dumps(details, ensure_ascii=False), event['applied'] != 'block',
             event['user_id'], event['save_id'], event['role'], event['character_id']),
        )
        return int(cursor.lastrowid)
