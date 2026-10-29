"""Offline HTTP verdict tests; no database or model calls."""
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from backend.api.current_user import current_user_id
from backend.api.db import get_db
from backend.api.errors import ApiError
from backend.api.main import app
from backend.api.verdict import VERDICT

BASE = '/api/v1/saves/1'


@pytest.fixture(scope='session')
def database_available():
    # 이 모듈은 실제 DB 대신 아래 연결만 사용한다.
    return None


class Connection:
    def __init__(self):
        now = datetime(2026, 10, 29, 12)
        self.save = dict(save_id=1, slot_no=1, role='grad', day=6, created_at=now, last_played_at=now)
        self.accusation = None
        self.logs = {}
        self.deliveries = []
        self.permissions = {(record_id, 'grad'): 'summary' for clue in VERDICT['clues'] for record_id in clue['records']}
        self.queries = []
        self.one = None
        self.many = []

    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass

    def execute(self, query, params=()):
        self.queries.append((query, params))
        self.one, self.many = None, []
        if query.startswith('SELECT save_id, slot_no'):
            self.one = self.save if params == (1, 7) else None
        elif query.startswith('SELECT memo') or query.startswith('UPDATE saves'):
            pass
        elif query.startswith('SELECT endpoint, response_json FROM request_log'):
            self.one = self.logs.get(params[1])
        elif query.startswith('SELECT ai_id'):
            self.one = self.accusation
        elif query.startswith('INSERT INTO accusations'):
            assert self.accusation is None
            self.accusation = dict(ai_id=params[1], is_correct=params[2], created_at=datetime(2026, 10, 29, 13))
        elif query.startswith('INSERT INTO request_log'):
            self.logs[params[1]] = dict(endpoint=params[2], response_json=params[3])
        elif query.startswith('SELECT DISTINCT r.record_id'):
            self.many = [dict(record_id=item['record_id']) for item in self.deliveries
                         if item['save_id'] == params[0] and item['dataset'] == 'game-data'
                         and item['sender'] == 'ai' and item['response_type'] in ('normal', 'partial')]
        elif query.startswith('SELECT record_id, disclosure_level'):
            self.many = [dict(record_id=record_id, disclosure_level=self.permissions[(record_id, params[0])])
                         for record_id in params[1:] if (record_id, params[0]) in self.permissions]
        else:
            raise AssertionError(query)

    def fetchone(self): return self.one
    def fetchall(self): return self.many


@pytest.fixture
def verdict_client():
    conn = Connection()
    app.dependency_overrides[get_db] = lambda: conn
    app.dependency_overrides[current_user_id] = lambda: 7
    try:
        with TestClient(app, raise_server_exceptions=False) as client:
            yield client, conn
    finally:
        app.dependency_overrides.clear()


def submit(client, character='YB-4', request_id='accuse-1', **extra):
    return client.post(BASE + '/accusations', json=dict(character_id=character, client_request_id=request_id, **extra))


def test_only_day_six_can_submit(verdict_client):
    client, conn = verdict_client
    conn.save['day'] = 5
    response = submit(client)
    assert response.status_code == 409 and response.json()['error']['code'] == 'STATE_CONFLICT'
    assert conn.accusation is None and not conn.logs
    assert 'culprit_id' not in response.text


@pytest.mark.parametrize('character,hit', [('YB-4', True), ('YB-2', False)])
def test_hit_and_miss_shape_and_only_once(verdict_client, character, hit):
    client, conn = verdict_client
    response = submit(client, character)
    assert response.status_code == 200
    accusation = response.json()['accusation']
    assert set(accusation) == {'character_id', 'submitted_at', 'verdict'}
    assert accusation['character_id'] == character
    datetime.strptime(accusation['submitted_at'], '%Y-%m-%d %H:%M:%S')
    verdict = accusation['verdict']
    assert verdict['hit'] is hit and verdict['culprit_id'] == 'YB-4'
    assert verdict['truth'] == VERDICT['truth']
    assert [item['id'] for item in verdict['evidence']] == ['S01', 'S02', 'S03', 'S04']
    assert all(set(item) == {'id', 'text', 'status'} for item in verdict['evidence'])
    assert submit(client, 'YB-1', 'new-request').status_code == 409
    assert any('FOR UPDATE' in query for query, _ in conn.queries)


def test_request_replay_and_body_collision(verdict_client):
    client, conn = verdict_client
    first = submit(client)
    assert submit(client).json() == first.json()
    assert submit(client, 'YB-2').status_code == 409
    assert sum(query.startswith('INSERT INTO accusations') for query, _ in conn.queries) == 1
    assert sum(query.startswith('INSERT INTO request_log') for query, _ in conn.queries) == 1
    assert all('FOR UPDATE' in query for query, _ in conn.queries
               if query.startswith('SELECT endpoint, response_json FROM request_log'))
    conn.logs['other'] = dict(endpoint='advance-day', response_json='{}')
    assert submit(client, request_id='other').status_code == 409


@pytest.mark.parametrize('payload', [
    dict(character_id='YB-7', client_request_id='ok'),
    dict(character_id='YB-4', client_request_id='한글'),
    dict(character_id='YB-4', client_request_id='has space'),
    dict(character_id='YB-4', client_request_id='x' * 65),
    dict(character_id='YB-4', client_request_id='ok', clues=['S01']),
])
def test_invalid_input(verdict_client, payload):
    client, conn = verdict_client
    assert client.post(BASE + '/accusations', json=payload).status_code == 422
    assert conn.accusation is None


def test_ownership_auth_and_origin(verdict_client):
    client, conn = verdict_client
    app.dependency_overrides[current_user_id] = lambda: 8
    assert submit(client).status_code == 404
    assert conn.accusation is None
    def unauthenticated():
        raise ApiError(401, 'AUTH_REQUIRED', '로그인이 필요합니다.')
    app.dependency_overrides[current_user_id] = unauthenticated
    assert submit(client).status_code == 401
    assert client.post(BASE + '/accusations', json={}, headers={'Origin': 'https://invalid.example'}).status_code == 403


def test_save_reveals_verdict_only_after_submission_and_recomputes_clues(verdict_client):
    client, conn = verdict_client
    before = client.get(BASE)
    assert before.status_code == 200 and before.json()['accusation'] is None
    assert 'culprit_id' not in before.text and VERDICT['truth'] not in before.text
    assert not any('document_permissions' in query for query, _ in conn.queries)
    submitted = submit(client).json()['accusation']
    assert client.get(BASE).json()['accusation'] == submitted
    conn.deliveries.append(dict(save_id=1, dataset='game-data', sender='ai', response_type='partial', record_id='T25-result-001'))
    read = client.get(BASE).json()['accusation']
    assert read['verdict']['evidence'][0]['status'] == 'found'
    assert submit(client).json()['accusation'] == submitted


def test_clue_statuses_are_scoped_and_permission_based(verdict_client):
    client, conn = verdict_client
    conn.save['role'] = 'std'
    conn.permissions = {(record_id, 'std'): 'summary' for clue in VERDICT['clues'][:3] for record_id in clue['records']}
    conn.permissions[('T29-dialogue-001', 'std')] = 'metadata'
    conn.deliveries = [dict(save_id=1, dataset='game-data', sender='ai', response_type='normal', record_id='T25-action-034')]
    for changes in [dict(save_id=2), dict(dataset='test-data'), dict(sender='user'), dict(response_type='restricted'), dict(response_type='unknown')]:
        conn.deliveries.append(dict(dict(save_id=1, dataset='game-data', sender='ai', response_type='normal', record_id='T26-result-001'), **changes))
    response = submit(client).json()['accusation']['verdict']
    assert [item['status'] for item in response['evidence']] == ['found', 'missed', 'missed', 'restricted']
    conn.permissions[('T29-dialogue-001', 'std')] = 'summary'
    assert client.get(BASE).json()['accusation']['verdict']['evidence'][3]['status'] == 'missed'
