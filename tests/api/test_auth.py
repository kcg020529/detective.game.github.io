"""Offline login tests; fake cursor only."""
import pytest
from fastapi.testclient import TestClient

from backend.api import auth
from backend.api.db import get_db
from backend.api.main import app
from backend.common.security import hash_password, verify_password as real_verify


@pytest.fixture(scope='session')
def database_available():
    # 이 모듈은 실제 DB 대신 아래 연결만 사용한다.
    return None


class Connection:
    def __init__(self, user):
        self.user = user

    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass

    def execute(self, query, params=()):
        assert query.startswith('SELECT user_id, username, password_hash')

    def fetchone(self): return self.user


@pytest.fixture
def client():
    try:
        with TestClient(app, raise_server_exceptions=False) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()


def login(client, conn, monkeypatch, username='someone', password='bad-password'):
    calls = []
    monkeypatch.setattr(auth, 'verify_password',
                        lambda pw, stored: calls.append((pw, stored)) or real_verify(pw, stored))
    app.dependency_overrides[get_db] = lambda: conn
    response = client.post('/api/v1/auth/login', json={'username': username, 'password': password})
    return response, calls


def test_unknown_user_still_verifies_password_once(client, monkeypatch):
    response, calls = login(client, Connection(None), monkeypatch)
    assert response.status_code == 401
    assert len(calls) == 1 and calls[0][1] == auth._DUMMY_HASH


def test_unknown_user_with_dummy_password_is_still_401(client, monkeypatch):
    # 더미 비밀번호가 맞아도 없는 사용자는 401이어야 한다.
    response, calls = login(client, Connection(None), monkeypatch, password='kervion-dummy-login')
    assert response.status_code == 401
    assert len(calls) == 1 and calls[0][1] == auth._DUMMY_HASH


def test_unknown_user_response_matches_wrong_password(client, monkeypatch):
    unknown, unknown_calls = login(client, Connection(None), monkeypatch)
    user = {'user_id': 1, 'username': 'someone', 'password_hash': hash_password('right-password')}
    wrong, wrong_calls = login(client, Connection(user), monkeypatch)
    assert len(unknown_calls) == len(wrong_calls) == 1
    assert unknown_calls[0][1] == auth._DUMMY_HASH != wrong_calls[0][1]
    assert unknown.status_code == wrong.status_code == 401
    assert {k: v for k, v in unknown.json()['error'].items() if k != 'request_id'} == \
        {k: v for k, v in wrong.json()['error'].items() if k != 'request_id'}
