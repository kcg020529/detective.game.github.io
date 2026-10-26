import json
import tempfile
import uuid
from pathlib import Path

import pytest
from qdrant_client import QdrantClient, models

from backend.rag.chunking import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, chunk_text
from backend.rag.embedder import MODEL_NAME, VECTOR_SIZE
from backend.rag.errors import RagRequestError, RagUnavailable
from backend.rag.index import COLLECTIONS, MANIFEST, index_dataset, table_checksums
from backend.rag import search

KNOWN_LOCATION = next(iter(search.LOCATIONS))


class FakeEmbedder:
    def embed_query(self, text):
        return [1.0] + [0.0] * (VECTOR_SIZE - 1)

    def count_tokens(self, text):
        return len(text.split()) + 2

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]


class FakeCursor:
    def __init__(self):
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, *_):
        self.rows = [{'Table': f'kervion.{table}', 'Checksum': number} for number, table in enumerate(
            ('game_records', 'game_record_ai', 'game_record_locations'), 1)]

    def fetchall(self):
        return self.rows


class FakeConnection:
    def cursor(self):
        return FakeCursor()


class Scope:
    def __init__(self, disclosures):
        self.disclosures = disclosures


@pytest.fixture
def qdrant():
    client = QdrantClient(':memory:')
    client.create_collection(COLLECTIONS['game-data'], vectors_config=models.VectorParams(
        size=VECTOR_SIZE, distance=models.Distance.COSINE))
    client.create_collection(MANIFEST, vectors_config=models.VectorParams(size=1, distance=models.Distance.DOT))
    manifest_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))
    client.upsert(collection_name=MANIFEST, points=[models.PointStruct(
        id=manifest_id, vector=[0.0], payload={'dataset': 'game-data', 'checksums': table_checksums(FakeConnection()),
                                              'model_name': MODEL_NAME, 'max_tokens': CHUNK_MAX_TOKENS,
                                              'overlap_tokens': CHUNK_OVERLAP_TOKENS})])
    yield client
    client.close()


def add_point(client, rid, kind, *, record_type='Action', day=1, test_id=1, loc='중앙 홀', ai='YB-2',
              score_vector=None, text=None):
    client.upsert(collection_name=COLLECTIONS['game-data'], points=[models.PointStruct(
        id=str(uuid.uuid5(uuid.NAMESPACE_URL, f'{rid}:{kind}')),
        vector=score_vector or [1.0] + [0.0] * (VECTOR_SIZE - 1),
        payload={'dataset': 'game-data', 'record_id': rid, 'kind': kind, 'chunk_no': 0,
                 'record_type': record_type, 'day': day, 'test_id': test_id,
                 'location_ids': [loc], 'related_ai_ids': [ai]},
    )])


def run_search(monkeypatch, client, disclosures, plan=None):
    calls = {'query': 0, 'resolve': None}

    class Repository:
        ids = None

        def __init__(self, _conn):
            pass

        def search_scope(self, **_):
            return Scope(disclosures)

        def resolve(self, **kwargs):
            calls['resolve'] = kwargs['record_ids']
            return [{'record_id': rid, 'summary': 'safe'} for rid in kwargs['record_ids']]

    monkeypatch.setattr(search, 'PolicyRepository', Repository)
    original = client.query_points_groups

    def tracked(*args, **kwargs):
        calls['query'] += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(client, 'query_points_groups', tracked)
    result = search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                                   dataset='game-data', plan=plan or {'query': 'query'},
                                   qdrant=client, embedder=FakeEmbedder())
    return result, calls


def test_level_filter_blocks_body_points(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta')
    add_point(qdrant, 'T01-action-001', 'summary')
    add_point(qdrant, 'T01-action-001', 'content')
    result, _ = run_search(monkeypatch, qdrant, [('T01-action-001', 'metadata')])
    assert [row['record_id'] for row in result] == ['T01-action-001']
    result, _ = run_search(monkeypatch, qdrant, [('T01-action-001', 'summary')])
    assert [row['record_id'] for row in result] == ['T01-action-001']
    assert qdrant.count(COLLECTIONS['game-data'], count_filter=models.Filter(must=[
        models.FieldCondition(key='record_id', match=models.MatchValue(value='T01-action-001')),
        models.FieldCondition(key='kind', match=models.MatchValue(value='content'))])).count == 1


def test_out_of_scope_best_match_never_returned(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta')
    add_point(qdrant, 'T01-action-002', 'meta', score_vector=[0.0, 1.0] + [0.0] * (VECTOR_SIZE - 2))
    result, calls = run_search(monkeypatch, qdrant, [('T01-action-001', 'metadata')])
    assert [row['record_id'] for row in result] == ['T01-action-001']
    assert calls['resolve'] == ['T01-action-001']


def test_empty_scope_does_not_call_qdrant(monkeypatch, qdrant):
    result, calls = run_search(monkeypatch, qdrant, [])
    assert result == [] and calls['query'] == 0


@pytest.mark.parametrize(('field', 'value', 'keep'), [
    ('record_types', ['Dialogue'], 'T01-dialogue-001'),
    ('location_ids', [KNOWN_LOCATION], 'T01-action-002'),
    ('test_ids', [2], 'T02-action-001'),
    ('related_ai_ids', ['YB-3'], 'T01-action-003'),
])
def test_planner_filters_narrow(monkeypatch, qdrant, field, value, keep):
    ids = ['T01-dialogue-001', 'T01-action-002', 'T02-action-001', 'T01-action-003']
    for rid in ids:
        add_point(qdrant, rid, 'meta', record_type='Dialogue' if rid.endswith('001') and 'dialogue' in rid else 'Action',
                  test_id=2 if rid.startswith('T02') else 1,
                  loc=KNOWN_LOCATION if rid.endswith('002') else 'other-location', ai='YB-3' if rid.endswith('003') else 'YB-2')
    scope = [(rid, 'metadata') for rid in ids]
    result, _ = run_search(monkeypatch, qdrant, scope, {'query': 'q', field: value})
    assert [row['record_id'] for row in result] == [keep]


def test_empty_planner_arrays_do_not_filter(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta')
    result, _ = run_search(monkeypatch, qdrant, [('T01-action-001', 'metadata')], {
        'query': 'q', 'record_types': [], 'location_ids': [], 'test_ids': [], 'related_ai_ids': []})
    assert len(result) == 1


def test_result_order_and_projection_come_from_resolve(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta', score_vector=[0.0, 1.0] + [0.0] * (VECTOR_SIZE - 2))
    add_point(qdrant, 'T01-action-002', 'meta')
    resolved = [{'record_id': 'T01-action-002', 'safe': True}, {'record_id': 'T01-action-001', 'safe': True}]

    class Repository:
        def __init__(self, _conn):
            pass

        def search_scope(self, **_):
            return Scope([('T01-action-001', 'metadata'), ('T01-action-002', 'metadata')])

        def resolve(self, **kwargs):
            Repository.ids = kwargs['record_ids']
            return resolved

    monkeypatch.setattr(search, 'PolicyRepository', Repository)
    result = search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                                   dataset='game-data', plan={'query': 'q'}, qdrant=qdrant,
                                   embedder=FakeEmbedder())
    assert result == resolved
    assert Repository.ids == ['T01-action-002', 'T01-action-001']
    assert [row['record_id'] for row in result] == ['T01-action-002', 'T01-action-001']
    assert all(set(row) == {'record_id', 'safe'} for row in result)


def test_limit_applies_after_resolve_with_up_to_100_candidates(monkeypatch, qdrant):
    ids = [f'T01-action-{number:03}' for number in range(1, 9)]
    for rid in ids:
        add_point(qdrant, rid, 'meta')

    class Repository:
        received = None

        def __init__(self, _conn):
            pass

        def search_scope(self, **_):
            return Scope([(rid, 'metadata') for rid in ids])

        def resolve(self, **kwargs):
            Repository.received = kwargs['record_ids']
            return [{'record_id': rid} for index, rid in enumerate(kwargs['record_ids']) if index % 2 == 0]

    monkeypatch.setattr(search, 'PolicyRepository', Repository)
    result = search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                                  dataset='game-data', plan={'query': 'q', 'limit': 3}, qdrant=qdrant,
                                  embedder=FakeEmbedder())
    assert len(Repository.received) == 8 <= 100
    assert len(result) == 3
    assert [row['record_id'] for row in result] == [Repository.received[index] for index in (0, 2, 4)]


def test_planner_v1_contract_query_and_length_limits():
    plan = {
        'query': '\uccab\ub0a0 YB-2\uc758 \ud589\ub3d9',
        'record_types': ['Action'], 'test_ids': [1, 2, 3, 4, 5],
        'location_ids': [], 'related_ai_ids': ['YB-2'], 'limit': 5,
    }
    assert search.validate_plan(plan) == plan
    assert search.validate_plan({'query': 'x' * 2000})['query'] == 'x' * 2000
    with pytest.raises(RagRequestError):
        search.validate_plan({'query': 'x' * 2001})
    with pytest.raises(RagRequestError):
        search.validate_plan({'query': '   '})


@pytest.mark.parametrize('plan', [
    {}, {'query': '   '}, {'query': 'q', 'unknown': 1}, {'query': 'q', 'limit': True},
    {'query': 'q', 'limit': 21}, {'query': 'q', 'test_ids': [True]},
    {'query': 'q', 'test_ids': [1, 1]}, {'query': 'q', 'record_types': ['bogus']},
    {'query': 'q', 'related_ai_ids': ['YB-2', 'YB-2']},
])
def test_invalid_plan(plan):
    with pytest.raises(RagRequestError):
        search.validate_plan(plan)


@pytest.mark.parametrize('missing', [True, False])
def test_missing_or_stale_manifest_fails_closed(qdrant, monkeypatch, missing):
    if missing:
        qdrant.delete(collection_name=MANIFEST, points_selector=models.PointIdsList(points=[
            str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))]))
    else:
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))
        qdrant.upsert(collection_name=MANIFEST, points=[models.PointStruct(
            id=point_id, vector=[0.0], payload={'dataset': 'game-data', 'checksums': {'game_records': 99}})])
    monkeypatch.setattr(search, 'PolicyRepository', lambda _: type('R', (), {
        'search_scope': lambda self, **_: Scope([('T01-action-001', 'metadata')])})())
    with pytest.raises(RagUnavailable) as exc:
        search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2', dataset='game-data',
                              plan={'query': 'q'}, qdrant=qdrant, embedder=FakeEmbedder())
    assert exc.value.code == 'INDEX_STALE'


def test_manifest_chunk_setting_mismatch_fails_closed(qdrant, monkeypatch):
    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))
    qdrant.upsert(collection_name=MANIFEST, points=[models.PointStruct(
        id=point_id, vector=[0.0], payload={
            'dataset': 'game-data', 'checksums': table_checksums(FakeConnection()), 'model_name': MODEL_NAME,
            'max_tokens': CHUNK_MAX_TOKENS + 1, 'overlap_tokens': CHUNK_OVERLAP_TOKENS,
        })])
    monkeypatch.setattr(search, 'PolicyRepository', lambda _: type('R', (), {
        'search_scope': lambda self, **_: Scope([('T01-action-001', 'metadata')])})())
    with pytest.raises(RagUnavailable) as exc:
        search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2', dataset='game-data',
                              plan={'query': 'q'}, qdrant=qdrant, embedder=FakeEmbedder())
    assert exc.value.code == 'INDEX_STALE'


def test_query_token_limit_fails_before_policy_and_qdrant(monkeypatch, qdrant):
    calls = {'scope': 0, 'qdrant': 0}

    class Repository:
        def __init__(self, _conn):
            pass

        def search_scope(self, **_):
            calls['scope'] += 1
            return Scope([])

    class QdrantSpy:
        def __getattr__(self, name):
            value = getattr(qdrant, name)
            if not callable(value):
                return value

            def call(*args, **kwargs):
                calls['qdrant'] += 1
                return value(*args, **kwargs)
            return call

    monkeypatch.setattr(search, 'PolicyRepository', Repository)
    with pytest.raises(RagRequestError) as exc:
        search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                              dataset='game-data', plan={'query': 'x ' * 127}, qdrant=QdrantSpy(),
                              embedder=FakeEmbedder())
    assert exc.value.code == 'QUERY_TOO_LONG'
    assert calls == {'scope': 0, 'qdrant': 0}

    result = search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                                   dataset='game-data', plan={'query': 'x ' * 126}, qdrant=QdrantSpy(),
                                   embedder=FakeEmbedder())
    assert result == []
    assert calls == {'scope': 1, 'qdrant': 0}


class ChangingChecksumCursor(FakeCursor):
    def __init__(self, connection):
        super().__init__()
        self.connection = connection

    def execute(self, query, *_):
        if query.startswith('CHECKSUM TABLE'):
            self.connection.checks += 1
            self.connection.events.append('checksum')
            checksum = self.connection.checks
            self.rows = [{'Table': f'kervion.{table}', 'Checksum': index + checksum} for index, table in enumerate(
                ('game_records', 'game_record_ai', 'game_record_locations'), 1)]
        else:
            self.connection.events.append(query)
            self.rows = []


class ChangingChecksumConnection:
    def __init__(self):
        self.checks = 0
        self.events = []

    def cursor(self):
        return ChangingChecksumCursor(self)


def test_index_checksum_change_leaves_manifest_missing_and_search_stale(monkeypatch, qdrant):
    connection = ChangingChecksumConnection()
    with pytest.raises(RuntimeError, match='Database changed during indexing'):
        index_dataset(connection, qdrant, 'game-data', FakeEmbedder())
    assert connection.events == [
        'checksum', 'SELECT dataset, record_id, record_type, test_id, day, summary, content FROM game_records WHERE dataset = %s ORDER BY record_id',
        'SELECT record_id, ai_id, relation_kind FROM game_record_ai WHERE dataset = %s ORDER BY record_id, ai_id, relation_kind',
        'SELECT record_id, location_id FROM game_record_locations WHERE dataset = %s ORDER BY record_id, location_id',
        'checksum',
    ]
    manifest_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))
    assert qdrant.retrieve(collection_name=MANIFEST, ids=[manifest_id], with_payload=True) == []

    monkeypatch.setattr(search, 'PolicyRepository', lambda _: type('R', (), {
        'search_scope': lambda self, **_: Scope([('T01-action-001', 'metadata')])})())
    with pytest.raises(RagUnavailable) as exc:
        search.search_records(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                              dataset='game-data', plan={'query': 'q'}, qdrant=qdrant,
                              embedder=FakeEmbedder())
    assert exc.value.code == 'INDEX_STALE'


def test_chunk_limits_and_source_coverage():
    text = '\n'.join(f'line {i} alpha beta gamma' for i in range(100))
    chunks = chunk_text(text, FakeEmbedder().count_tokens, max_tokens=20, overlap_tokens=2)
    assert all(FakeEmbedder().count_tokens(chunk) <= 20 for chunk in chunks)
    position = 0
    for chunk in chunks:
        start = text.find(chunk, position)
        if start < 0:
            start = text.find(chunk, max(0, position - 100))
        assert start >= 0
        position = max(position, start + len(chunk))
    assert position == len(text)


def test_real_tokenizer_chunk_limit():
    from fastembed import TextEmbedding
    from backend.rag.embedder import FastEmbedder

    model_dir = (Path(tempfile.gettempdir()) / 'fastembed_cache' /
                 'models--Qdrant--paraphrase-multilingual-MiniLM-L12-v2-onnx-Q' / 'snapshots')
    if not model_dir.is_dir() or not any(model_dir.iterdir()):
        pytest.skip('fastembed tokenizer model is not cached locally')
    TextEmbedding(MODEL_NAME, local_files_only=True)
    embedder = FastEmbedder()
    data = json.loads((Path(__file__).resolve().parents[2] / 'data' / 'test-data' / 'records.json')
                      .read_text(encoding='utf-8'))
    text = ''.join(f'{i} {data[0]["summary"]}\n{data[0]["content"]}\n' for i in range(300))
    chunks = chunk_text(text, embedder.count_tokens)
    assert embedder.count_tokens(text) > 128
    assert len(chunks) > 1
    assert all(embedder.count_tokens(chunk) <= 128 for chunk in chunks)
    rebuilt = chunks[0]
    for chunk in chunks[1:]:
        overlap = max(i for i in range(min(len(rebuilt), len(chunk)) + 1)
                      if rebuilt.endswith(chunk[:i]))
        rebuilt += chunk[overlap:]
    assert rebuilt == text
