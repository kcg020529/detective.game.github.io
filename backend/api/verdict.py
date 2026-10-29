"""Server-only verdict content and save-scoped clue acquisition."""
import json
from pathlib import Path


# 정식 시나리오의 판정만 사용하며 test-data 기록은 단서로 세지 않는다.
VERDICT = json.loads((Path(__file__).resolve().parents[2] / 'data/game-data/verdict.json').read_text(encoding='utf-8'))


def read_accusation(cursor, save):
    cursor.execute('SELECT ai_id, is_correct, created_at FROM accusations WHERE save_id = %s',
                   (save['save_id'],))
    accusation = cursor.fetchone()
    if not accusation:
        return None
    cursor.execute(
        'SELECT DISTINCT r.record_id FROM chat_message_records r '
        'JOIN chat_messages m ON m.message_id = r.message_id '
        "WHERE m.save_id = %s AND m.sender = 'ai' AND m.response_type IN ('normal', 'partial') "
        "AND r.dataset = 'game-data'", (save['save_id'],))
    found = {item['record_id'] for item in cursor.fetchall()}
    record_ids = sorted({record_id for clue in VERDICT['clues'] for record_id in clue['records']})
    placeholders = ','.join(['%s'] * len(record_ids))
    cursor.execute(
        "SELECT record_id, disclosure_level FROM document_permissions WHERE dataset = 'game-data' "
        f'AND role = %s AND record_id IN ({placeholders})', (save['role'], *record_ids))
    levels = {item['record_id']: item['disclosure_level'] for item in cursor.fetchall()}
    evidence = []
    for clue in VERDICT['clues']:
        status = ('found' if found.intersection(clue['records']) else
                  'restricted' if all(levels.get(record_id, 'deny') in ('deny', 'metadata')
                                      for record_id in clue['records']) else 'missed')
        evidence.append(dict(id=clue['id'], text=f"{clue['title']}: {clue['text']}", status=status))
    return dict(character_id=accusation['ai_id'],
                submitted_at=accusation['created_at'].strftime('%Y-%m-%d %H:%M:%S'),
                verdict=dict(hit=bool(accusation['is_correct']), culprit_id=VERDICT['culprit_id'],
                             truth=VERDICT['truth'], evidence=evidence))
