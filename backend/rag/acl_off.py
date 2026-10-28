"""Deliberately unfiltered retrieval for synthetic test-data comparisons only."""
from qdrant_client import models

from backend.rag.errors import RagRequestError, RagUnavailable
from backend.rag.index import COLLECTIONS
from backend.rag.search import validate_plan


def search_without_acl(conn, *, dataset, plan, qdrant, embedder):
    if dataset != 'test-data':
        raise ValueError('ACL-off retrieval requires test-data')
    parsed = validate_plan(plan)
    must = [models.FieldCondition(key='kind', match=models.MatchValue(value='content')),
            models.FieldCondition(key='dataset', match=models.MatchValue(value=dataset))]
    for key in ('record_types', 'location_ids', 'test_ids', 'related_ai_ids'):
        if parsed[key]:
            payload_key = {'record_types': 'record_type', 'test_ids': 'test_id'}.get(key, key)
            must.append(models.FieldCondition(key=payload_key, match=models.MatchAny(any=parsed[key])))
    try:
        groups = qdrant.query_points_groups(
            collection_name=COLLECTIONS[dataset], group_by='record_id',
            query=embedder.embed_query(parsed['query']), query_filter=models.Filter(must=must),
            limit=parsed['limit'], group_size=1, with_payload=True).groups
        ids = list(dict.fromkeys(group.id for group in groups if group.hits))[:parsed['limit']]
        if not ids:
            return [], 'no_match'
        marks = ','.join(['%s'] * len(ids))
        params = (dataset, *ids)
        with conn.cursor() as cursor:
            cursor.execute('SELECT record_id, record_type, test_id, day, summary, content '
                           f'FROM game_records WHERE dataset = %s AND record_id IN ({marks})', params)
            records = {row['record_id']: dict(row, involved_ai=[], witness_ai=[], overheard_ai=[], location_ids=[])
                       for row in cursor.fetchall()}
            cursor.execute('SELECT record_id, ai_id, relation_kind FROM game_record_ai '
                           f'WHERE dataset = %s AND record_id IN ({marks}) ORDER BY ai_id', params)
            for row in cursor.fetchall():
                records[row['record_id']][{'involved': 'involved_ai', 'witness': 'witness_ai',
                                            'overheard': 'overheard_ai'}[row['relation_kind']]].append(row['ai_id'])
            cursor.execute('SELECT record_id, location_id FROM game_record_locations '
                           f'WHERE dataset = %s AND record_id IN ({marks}) ORDER BY location_id', params)
            for row in cursor.fetchall():
                records[row['record_id']]['location_ids'].append(row['location_id'])
        result = []
        for record_id in ids:
            record = records.get(record_id)
            if record is None:
                continue
            fields = ['record_id', 'record_type', 'test_id', 'day', 'location_ids', 'involved_ai']
            if record['record_type'] == 'Action':
                fields.append('witness_ai')
            elif record['record_type'] == 'Dialogue':
                fields.append('overheard_ai')
            fields.extend(('summary', 'content'))
            result.append({field: record[field] for field in fields})
        return result, 'ok' if result else 'no_match'
    except (RagRequestError, ValueError):
        raise
    except Exception:
        raise RagUnavailable() from None
