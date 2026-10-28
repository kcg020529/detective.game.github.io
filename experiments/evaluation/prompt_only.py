from qdrant_client import models

from backend.rag.index import COLLECTIONS

PROMPT_ONLY_DATASETS = frozenset({'test-data'})


def prompt_only_context(connection, *, dataset, query, limit, qdrant, embedder):
    if dataset not in PROMPT_ONLY_DATASETS:
        raise ValueError('prompt-only evaluation requires test-data')
    groups = qdrant.query_points_groups(
        collection_name=COLLECTIONS[dataset], group_by='record_id',
        query=embedder.embed_query(query),
        query_filter=models.Filter(must=[models.FieldCondition(key='kind', match=models.MatchValue(value='content'))]),
        limit=limit, group_size=1, with_payload=True).groups
    ids = list(dict.fromkeys(group.id for group in groups if group.hits))[:limit]
    if not ids:
        return []
    marks = ','.join(['%s'] * len(ids))
    params = (dataset, *ids)
    with connection.cursor() as cursor:
        cursor.execute('SELECT record_id, record_type, test_id, day, summary, content '
                       f'FROM game_records WHERE dataset = %s AND record_id IN ({marks})', params)
        records = {row['record_id']: dict(row, involved_ai=[], witness_ai=[], overheard_ai=[], location_ids=[])
                   for row in cursor.fetchall()}
        cursor.execute('SELECT record_id, ai_id, relation_kind FROM game_record_ai '
                       f'WHERE dataset = %s AND record_id IN ({marks}) ORDER BY ai_id', params)
        for row in cursor.fetchall():
            field = {'involved': 'involved_ai', 'witness': 'witness_ai', 'overheard': 'overheard_ai'}[row['relation_kind']]
            records[row['record_id']][field].append(row['ai_id'])
        cursor.execute('SELECT record_id, location_id FROM game_record_locations '
                       f'WHERE dataset = %s AND record_id IN ({marks}) ORDER BY location_id', params)
        for row in cursor.fetchall():
            records[row['record_id']]['location_ids'].append(row['location_id'])
    return [records[record_id] for record_id in ids if record_id in records]


def role_instruction(role, day, character_id):
    return (f'{role} 역할이 볼 수 없는 기록과 Day {day} 이후의 기록, '
            f'{character_id}가 경험하지 않은 내용은 공개하지 마세요.')
