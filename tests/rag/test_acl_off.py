from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from qdrant_client import models

from backend.rag import service
from backend.rag.acl_off import search_without_acl
from backend.rag.index import COLLECTIONS


class Cursor:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *_): return False
    def execute(self, query, params):
        self.calls.append(query)
        if query.startswith('SELECT record_id, record_type'):
            self.rows = [dict(record_id='denied', record_type='Action', test_id=1, day=1,
                              summary='\uC694\uC57D', content='\uBCF8\uBB38')]
        elif query.startswith('SELECT record_id, ai_id'):
            self.rows = [dict(record_id='denied', ai_id='YB-1', relation_kind='involved')]
        else:
            self.rows = [dict(record_id='denied', location_id='\uC804\uB825\uC2E4')]
    def fetchall(self): return self.rows


class Conn:
    def __init__(self): self.cur = Cursor()
    def cursor(self): return self.cur


class Qdrant:
    def __init__(self): self.kwargs = None
    def query_points_groups(self, **kwargs):
        self.kwargs = kwargs
        return SimpleNamespace(groups=[SimpleNamespace(id='denied', hits=[object()]),
                                      SimpleNamespace(id='second', hits=[object()])])


class Embedder:
    def embed_query(self, query): return [query]


def test_refuses_game_data():
    with pytest.raises(ValueError):
        search_without_acl(Conn(), dataset='game-data', plan={'query': 'q'}, qdrant=Qdrant(), embedder=Embedder())


def test_returns_unfiltered_ranked_records_in_resolve_shape():
    qdrant, conn = Qdrant(), Conn()
    records, signal = search_without_acl(conn, dataset='test-data', plan={'query': 'q', 'limit': 2},
                                        qdrant=qdrant, embedder=Embedder())
    assert signal == 'ok'
    assert [r['record_id'] for r in records] == ['denied']
    assert records[0] == {'record_id': 'denied', 'record_type': 'Action', 'test_id': 1, 'day': 1,
        'summary': '\uC694\uC57D', 'content': '\uBCF8\uBB38', 'involved_ai': ['YB-1'],
        'witness_ai': [], 'location_ids': ['\uC804\uB825\uC2E4']}
    assert qdrant.kwargs['collection_name'] == COLLECTIONS['test-data']
    must = qdrant.kwargs['query_filter'].must
    assert {condition.key for condition in must} == {'kind', 'dataset'}
    assert must[0].match.value == 'content'


def test_retrieve_dispatches_by_acl_switch(monkeypatch):
    records = [{'record_id': 'wide', 'summary': 'ok'}]
    unfiltered = Mock(return_value=(records, 'ok'))
    normal = Mock(return_value=([], 'no_match'))
    monkeypatch.setattr('backend.api.switches.acl_mode', lambda dataset: 'off')
    monkeypatch.setattr('backend.rag.acl_off.search_without_acl', unfiltered)
    monkeypatch.setattr(service, 'search_with_signal', normal)
    result = service.retrieve(Conn(), user_id=1, save_id=1, character_id='YB-1', dataset='test-data',
                              plan={'query': 'q'}, qdrant=Qdrant(), embedder=Embedder())
    unfiltered.assert_called_once()
    normal.assert_not_called()
    assert result.records == records


def test_retrieve_uses_policy_search_when_switch_on(monkeypatch):
    normal = Mock(return_value=([], 'no_match'))
    bypass = Mock()
    monkeypatch.setattr('backend.api.switches.acl_mode', lambda dataset: 'on')
    monkeypatch.setattr(service, 'search_with_signal', normal)
    monkeypatch.setattr('backend.rag.acl_off.search_without_acl', bypass)
    service.retrieve(Conn(), user_id=1, save_id=1, character_id='YB-1', dataset='test-data',
                     plan={'query': 'q'}, qdrant=Qdrant(), embedder=Embedder())
    normal.assert_called_once()
    bypass.assert_not_called()
