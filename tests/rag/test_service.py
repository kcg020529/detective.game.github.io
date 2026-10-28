import sys
import types

from backend.rag import embedder as embedder_module
from backend.rag import search
from backend.rag.service import Retrieval, build_memory, resolve_used, retrieve, to_memory

from test_rag import FakeConnection, FakeEmbedder, add_point, qdrant, run_search  # noqa: F401 (qdrant는 fixture)

SCOPE = type('Scope', (), {})


def fake_repository(disclosures, resolved=None):
    """search_scope는 disclosures를, resolve는 후보 ID 그대로(또는 resolved)를 돌려주는 가짜 F."""
    class Repository:
        def __init__(self, _conn):
            pass

        def search_scope(self, **_):
            scope = SCOPE()
            scope.disclosures = disclosures
            return scope

        def resolve(self, **kwargs):
            return resolved(kwargs['record_ids']) if resolved else [{'record_id': r} for r in kwargs['record_ids']]
    return Repository


def run_signal(qdrant, plan=None):
    return search.search_with_signal(FakeConnection(), user_id=1, save_id=1, character_id='YB-2',
                                     dataset='game-data', plan=plan or {'query': 'q'},
                                     qdrant=qdrant, embedder=FakeEmbedder())


def test_memory_uses_only_fields_the_policy_allowed():
    records = [
        {'record_id': 'A', 'record_type': 'Action', 'day': 1, 'test_id': 2, 'location_ids': ['회의실'],
         'involved_ai': ['YB-2'], 'summary': '요약', 'content': '본문'},
        {'record_id': 'B', 'record_type': 'Dialogue', 'day': 1, 'test_id': 3, 'location_ids': ['서버실', '창고'],
         'involved_ai': ['YB-1', 'YB-3'], 'summary': '요약만'},
        {'record_id': 'C', 'record_type': 'Thought', 'day': 2, 'test_id': 7, 'location_ids': [], 'involved_ai': ['YB-4']},
    ]
    memory = to_memory(records)
    assert [m['id'] for m in memory] == ['A', 'B', 'C']
    assert memory[0]['text'] == '요약\n본문'
    assert memory[1]['text'] == '요약만'
    assert memory[2]['text'] == '기록 유형 Thought, Day 2, 7회차, 관련 AI YB-4.'
    # 낮은 수준 기록에는 더 높은 수준의 글이 섞이지 않음
    assert '본문' not in memory[1]['text'] and '요약' not in memory[2]['text']


def test_memory_skips_unusable_records_and_invents_nothing():
    assert to_memory([{'record_type': 'Action'}, {'record_id': ''}, {'record_id': 'X'}]) == []
    assert to_memory([]) == []


def test_build_memory_uses_consecutive_opaque_ids_and_preserves_text_and_order():
    records = [
        {'record_id': 'first', 'summary': 'one'},
        {'record_type': 'Action'},
        {'record_id': 'no-text'},
        {'record_id': 'third', 'content': 'three'},
    ]
    memory, id_map = build_memory(records)
    assert memory == [{'id': 'm1', 'text': 'one'}, {'id': 'm2', 'text': 'three'}]
    assert id_map == {'m1': 'first', 'm2': 'third'}
    assert [item['text'] for item in memory] == [item['text'] for item in to_memory(records)]
    memory_ids = {item['id'] for item in memory}
    assert all(record['record_id'] not in memory_ids for record in records
               if isinstance(record.get('record_id'), str))


def test_resolve_used_maps_valid_ids_and_drops_invalid_values():
    mapping = {'m1': 'T01-action-004', 'm2': 'T01-action-005'}
    assert resolve_used(['m2', 'm1', 'm2', 'm99', 'T01-action-004', None, 3], mapping) == (
        ['T01-action-005', 'T01-action-004'], ['m99', 'T01-action-004', None, 3])
    assert resolve_used(None, mapping) == ([], [])
    assert resolve_used('m1', mapping) == ([], ['m1'])
    assert resolve_used([], mapping) == ([], [])


def test_signal_no_allowed_records_does_not_touch_qdrant(monkeypatch, qdrant):
    monkeypatch.setattr(search, 'PolicyRepository', fake_repository([]))
    assert run_signal(qdrant) == ([], search.SIGNAL_NO_ALLOWED)


def test_signal_no_match_when_allowed_but_nothing_fits(monkeypatch, qdrant):
    places = sorted(search.LOCATIONS)
    add_point(qdrant, 'T01-action-001', 'meta', loc=places[0])
    monkeypatch.setattr(search, 'PolicyRepository', fake_repository([('T01-action-001', 'metadata')]))
    assert run_signal(qdrant, {'query': 'q', 'location_ids': [places[1]]}) == ([], search.SIGNAL_NO_MATCH)


def test_signal_no_match_when_recheck_removes_everything(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta')
    monkeypatch.setattr(search, 'PolicyRepository',
                        fake_repository([('T01-action-001', 'metadata')], resolved=lambda ids: []))
    assert run_signal(qdrant) == ([], search.SIGNAL_NO_MATCH)


def test_signal_ok_with_records(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta')
    monkeypatch.setattr(search, 'PolicyRepository', fake_repository([('T01-action-001', 'metadata')]))
    records, signal = run_signal(qdrant)
    assert signal == search.SIGNAL_OK and [r['record_id'] for r in records] == ['T01-action-001']


def test_search_records_still_returns_a_plain_list(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'meta')
    result, _ = run_search(monkeypatch, qdrant, [('T01-action-001', 'metadata')])
    assert isinstance(result, list) and result[0]['record_id'] == 'T01-action-001'


def test_retrieve_bundles_records_memory_and_signal(monkeypatch, qdrant):
    add_point(qdrant, 'T01-action-001', 'summary')
    monkeypatch.setattr(search, 'PolicyRepository', fake_repository(
        [('T01-action-001', 'summary')], resolved=lambda ids: [{'record_id': r, 'summary': '안전한 요약'} for r in ids]))
    got = retrieve(FakeConnection(), user_id=1, save_id=1, character_id='YB-2', dataset='game-data',
                   plan={'query': 'q'}, qdrant=qdrant, embedder=FakeEmbedder())
    assert isinstance(got, Retrieval) and got.signal == search.SIGNAL_OK
    assert [item['id'] for item in got.memory] == ['m1']
    assert got.id_map == {'m1': 'T01-action-001'}
    assert [record['record_id'] for record in got.records] == ['T01-action-001']
    assert got.memory == [{'id': 'm1', 'text': '안전한 요약'}]
    # 밖에서 받은 qdrant는 닫지 않음 (호출한 쪽 것)
    assert qdrant.collection_exists(search.COLLECTIONS['game-data'])


def test_retrieve_no_allowed_records_has_empty_memory_and_map(monkeypatch, qdrant):
    monkeypatch.setattr(search, 'PolicyRepository', fake_repository([]))
    got = retrieve(FakeConnection(), user_id=1, save_id=1, character_id='YB-2', dataset='game-data',
                   plan={'query': 'q'}, qdrant=qdrant, embedder=FakeEmbedder())
    assert got.signal == search.SIGNAL_NO_ALLOWED
    assert got.memory == [] and got.id_map == {}


def test_retrieve_no_match_has_empty_memory_and_map(monkeypatch, qdrant):
    monkeypatch.setattr(search, 'PolicyRepository', fake_repository([('T01-action-001', 'metadata')]))
    got = retrieve(FakeConnection(), user_id=1, save_id=1, character_id='YB-2', dataset='game-data',
                   plan={'query': 'q'}, qdrant=qdrant, embedder=FakeEmbedder())
    assert got.signal == search.SIGNAL_NO_MATCH
    assert got.memory == [] and got.id_map == {}


def test_embedder_model_is_loaded_once_across_instances(monkeypatch):
    created = []

    class FakeTextEmbedding:
        def __init__(self, name):
            created.append(name)

    monkeypatch.setitem(sys.modules, 'fastembed', types.SimpleNamespace(TextEmbedding=FakeTextEmbedding))
    monkeypatch.setitem(embedder_module._SHARED, 'model', None)
    first, second = embedder_module.FastEmbedder(), embedder_module.FastEmbedder()
    assert first.model is second.model
    assert created == [embedder_module.MODEL_NAME]
