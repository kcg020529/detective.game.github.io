import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.audit.policy_flow import record_policy_denial
from backend.policy.engine import PolicyContext
from backend.policy.repository import PolicyRepository


CONTEXT = PolicyContext(7, 11, 7, 'std', 1, 'YB-1', 'game-data')


class Cursor:
    lastrowid = 29

    def __init__(self):
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, sql, params):
        self.calls.append((sql, params))


class Connection:
    def __init__(self):
        self.cursors = []

    def cursor(self):
        cursor = Cursor()
        self.cursors.append(cursor)
        return cursor


def record(record_id, *, day=1, involved=None):
    return dict(dataset='game-data', record_id=record_id, record_type='Action',
                test_id=1 if day == 1 else 6, day=day,
                involved_ai=involved or ['YB-1'], witness_ai=[], location_ids=[])


def permission(record_id, level='metadata'):
    return dict(dataset='game-data', record_id=record_id, role='std', disclosure_level=level)


def repository_with(records, permissions, on_denial):
    repository = PolicyRepository(Connection(), on_denial=on_denial)
    repository._context = lambda *_: CONTEXT
    repository._metadata = lambda *_, **__: (records, permissions)
    return repository


def test_presearch_audits_only_when_catalog_exists_and_all_records_denied():
    events = []
    denied_id = 'T06-action-001'
    repo = repository_with({denied_id: record(denied_id, day=2)},
                           {denied_id: permission(denied_id)},
                           lambda *args: events.append(args))
    assert repo.search_scope(user_id=7, save_id=11, character_id='YB-1').record_ids == ()
    assert events == [(CONTEXT, 'pre_search', {'FUTURE_DAY': 1})]

    events.clear()
    allowed_id = 'T01-action-001'
    repo = repository_with({allowed_id: record(allowed_id), denied_id: record(denied_id, day=2)},
                           {allowed_id: permission(allowed_id), denied_id: permission(denied_id)},
                           lambda *args: events.append(args))
    assert repo.search_scope(user_id=7, save_id=11, character_id='YB-1').record_ids == (allowed_id,)
    assert events == []

    # A future-test question is auditable even while other records are allowed.
    repo.search_scope(user_id=7, save_id=11, character_id='YB-1',
                      requested_filters={'test_ids': [6]})
    assert events == [(CONTEXT, 'pre_search', {'FUTURE_DAY': 1})]
    events.clear()
    repo.search_scope(user_id=7, save_id=11, character_id='YB-1',
                      requested_filters={'test_ids': [30]})
    assert events == []  # no matching record is a search miss, not a denial

    repo = repository_with({}, {}, lambda *args: events.append(args))
    assert repo.search_scope(user_id=7, save_id=11, character_id='YB-1').record_ids == ()
    assert events == []

    invalid = record('T01-action-001')
    invalid['location_ids'] = ['invalid-place']
    repo = repository_with({'T01-action-001': invalid},
                           {'T01-action-001': permission('T01-action-001')},
                           lambda *args: events.append(args))
    assert repo.search_scope(user_id=7, save_id=11, character_id='YB-1').record_ids == ()
    assert events == []  # malformed catalog metadata is not a player denial


def test_postsearch_audits_denied_candidates_once():
    events = []
    allowed_id, denied_id = 'T01-action-001', 'T06-action-001'
    repo = repository_with({allowed_id: record(allowed_id), denied_id: record(denied_id, day=2)},
                           {allowed_id: permission(allowed_id), denied_id: permission(denied_id)},
                           lambda *args: events.append(args))
    result = repo.resolve(user_id=7, save_id=11, character_id='YB-1',
                          record_ids=[allowed_id, denied_id])
    assert [item['record_id'] for item in result] == [allowed_id]
    assert events == [(CONTEXT, 'post_search', {'FUTURE_DAY': 1})]


def test_policy_audit_contains_counts_but_no_record_text_or_ids():
    conn = Connection()
    event_id = record_policy_denial(conn, CONTEXT, 'post_search',
                                    {'AI_SCOPE': 2, 'ROLE_DENIED': 1},
                                    request_id='policy_test')
    assert event_id == 29
    sql, params = conn.cursors[0].calls[0]
    assert 'INSERT INTO audit_events' in sql
    assert params[1:4] == ('policy_denial', 'deny', 0)
    assert params[5] is True
    assert json.loads(params[4]) == {
        'stage': 'post_search', 'reasons': {'AI_SCOPE': 2, 'ROLE_DENIED': 1},
        'denied_count': 3,
    }
    assert 'T01-action' not in str(params)
    assert 'secret' not in str(params)


@pytest.mark.parametrize('reasons', [
    {}, {'UNKNOWN_REASON': 1}, {'FUTURE_DAY': 0}, {'FUTURE_DAY': True},
    {'FUTURE_DAY': '1'},
])
def test_policy_audit_rejects_invalid_reason_counts(reasons):
    conn = Connection()
    with pytest.raises(ValueError):
        record_policy_denial(conn, CONTEXT, 'pre_search', reasons, request_id='policy_test')
    assert not conn.cursors


def test_pipeline_commits_policy_event_when_downstream_generation_fails(monkeypatch):
    from backend.api.chat_pipeline import ChatPipeline
    from backend.api.errors import ApiError
    from backend.planner.service import Planner
    import backend.rag.service as rag
    import qdrant_client

    monkeypatch.setattr(Planner, 'from_environment', lambda: SimpleNamespace(
        plan=lambda *args: SimpleNamespace(
            route='retrieve', search=SimpleNamespace(to_rag_request=lambda: {}))))
    monkeypatch.setattr(qdrant_client, 'QdrantClient', lambda **kwargs: SimpleNamespace(close=lambda: None))
    monkeypatch.setattr('backend.rag.embedder.FastEmbedder', lambda: object())
    def fake_retrieve(*args, **kwargs):
        kwargs['on_policy_denial'](CONTEXT, 'pre_search', {'FUTURE_DAY': 1})
        return rag.Retrieval([], [], 'no_allowed_records')
    monkeypatch.setattr(rag, 'retrieve', fake_retrieve)
    audit = Mock(return_value=1)
    monkeypatch.setattr('backend.api.chat_pipeline.record_policy_denial', audit)
    conn = Mock()
    with pytest.raises(ApiError):
        ChatPipeline(Mock(side_effect=RuntimeError('D unavailable')), Mock()).reply(
            conn=conn, question='future?', context=CONTEXT, history=[])
    audit.assert_called_once()
    conn.commit.assert_called_once()
