"""Policy-scoped vector retrieval for game records."""

import uuid

from qdrant_client import models

from backend.policy.engine import AIS, DATASETS, LOCATIONS, TYPES
from backend.policy.repository import PolicyDenied, PolicyRepository, PolicyUnavailable
from backend.rag.chunking import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
from backend.rag.errors import RagRequestError, RagUnavailable
from backend.rag.embedder import MODEL_NAME
from backend.rag.index import COLLECTIONS, MANIFEST, table_checksums

_PLAN_KEYS = {'query', 'record_types', 'location_ids', 'test_ids', 'related_ai_ids', 'limit'}


def validate_plan(plan):
    if not isinstance(plan, dict) or set(plan) - _PLAN_KEYS:
        raise RagRequestError()
    query = plan.get('query')
    if not isinstance(query, str) or len(query) > 2000 or not query.strip():
        raise RagRequestError()
    choices = {
        'record_types': TYPES,
        'location_ids': LOCATIONS,
        'related_ai_ids': AIS,
    }
    normalized = {'query': query, 'limit': plan.get('limit', 5)}
    for key, allowed in choices.items():
        value = plan.get(key, [])
        if (not isinstance(value, list) or any(not isinstance(item, str) or item not in allowed for item in value)
                or len(value) != len(set(value))):
            raise RagRequestError()
        normalized[key] = value
    test_ids = plan.get('test_ids', [])
    if (not isinstance(test_ids, list) or any(type(value) is not int or not 1 <= value <= 30 for value in test_ids)
            or len(test_ids) != len(set(test_ids))):
        raise RagRequestError()
    normalized['test_ids'] = test_ids
    if type(normalized['limit']) is not int or not 1 <= normalized['limit'] <= 20:
        raise RagRequestError()
    return normalized


def _manifest_is_current(connection, qdrant, dataset):
    try:
        if not qdrant.collection_exists(MANIFEST):
            return False
        point_id = uuid.uuid5(uuid.NAMESPACE_URL, f'kervion-rag-manifest:{dataset}')
        result = qdrant.retrieve(collection_name=MANIFEST, ids=[str(point_id)], with_payload=True)
        if not result or result[0].payload.get('dataset') != dataset:
            return False
        payload = result[0].payload
        return (payload.get('checksums') == table_checksums(connection)
                and payload.get('model_name') == MODEL_NAME
                and payload.get('max_tokens') == CHUNK_MAX_TOKENS
                and payload.get('overlap_tokens') == CHUNK_OVERLAP_TOKENS)
    except (PolicyDenied, PolicyUnavailable):
        raise
    except Exception:
        raise RagUnavailable('INDEX_STALE') from None


def search_records(conn, *, user_id, save_id, character_id, dataset, plan, qdrant, embedder):
    parsed = validate_plan(plan)
    try:
        if embedder.count_tokens(parsed['query']) > CHUNK_MAX_TOKENS:
            raise RagRequestError('QUERY_TOO_LONG')
    except RagRequestError:
        raise
    except Exception:
        raise RagUnavailable() from None
    if dataset not in DATASETS:
        raise RagRequestError()
    repository = PolicyRepository(conn)
    try:
        scope = repository.search_scope(user_id=user_id, save_id=save_id,
                                        character_id=character_id, dataset=dataset)
    except (PolicyDenied, PolicyUnavailable):
        raise
    if not scope.disclosures:
        return []
    if not _manifest_is_current(conn, qdrant, dataset):
        raise RagUnavailable('INDEX_STALE')

    level_ids = {'metadata': [], 'summary': [], 'full': []}
    for record_id, level in scope.disclosures:
        level_ids[level].append(record_id)
    access = []
    for level, kind in (('metadata', 'meta'), ('summary', 'summary'), ('full', 'content')):
        if level_ids[level]:
            access.append(models.Filter(must=[models.FieldCondition(key='kind', match=models.MatchValue(value=kind)),
                                              models.FieldCondition(key='record_id', match=models.MatchAny(any=level_ids[level]))]))
    must = [models.FieldCondition(key='dataset', match=models.MatchValue(value=dataset)),
            models.Filter(should=access)]
    for key in ('record_types', 'location_ids', 'test_ids', 'related_ai_ids'):
        values = parsed[key]
        if values:
            payload_key = {'record_types': 'record_type', 'test_ids': 'test_id'}.get(key, key)
            must.append(models.FieldCondition(key=payload_key, match=models.MatchAny(any=values)))
    try:
        vector = embedder.embed_query(parsed['query'])
        grouped = qdrant.query_points_groups(
            collection_name=COLLECTIONS[dataset], group_by='record_id', query=vector,
            query_filter=models.Filter(must=must), limit=100, group_size=1,
            with_payload=True,
        )
    except (PolicyDenied, PolicyUnavailable):
        raise
    except Exception:
        raise RagUnavailable() from None
    ranked_ids = []
    for group in grouped.groups:
        if group.hits and group.id not in ranked_ids:
            ranked_ids.append(group.id)
    if not ranked_ids:
        return []
    try:
        resolved = repository.resolve(user_id=user_id, save_id=save_id, character_id=character_id,
                                       dataset=dataset, record_ids=ranked_ids)
        return resolved[:parsed['limit']]
    except (PolicyDenied, PolicyUnavailable):
        raise

