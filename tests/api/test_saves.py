from datetime import datetime

import pytest

from backend.api.db import connect_db, get_db
from backend.api.main import app


BASE = '/api/v1'


def assert_error(response, status, code):
    assert response.status_code == status
    error = response.json()['error']
    assert error['code'] == code
    assert error['message']
    assert error['request_id'].startswith('req_')


def create_save(client, slot_no=1, role='grad', overwrite=False, headers=None):
    return client.post(f'{BASE}/saves', json={
        'slot_no': slot_no, 'role': role, 'overwrite': overwrite,
    }, headers=headers)


def test_empty_list_and_create_shape(api_client):
    client, _, _ = api_client
    assert client.get(f'{BASE}/saves').json() == {'saves': []}
    response = create_save(client)
    assert response.status_code == 201
    save = response.json()
    assert set(save) == {'save_id', 'slot_no', 'role', 'day', 'created_at', 'last_played_at'}
    assert save['slot_no'] == 1 and save['role'] == 'grad' and save['day'] == 1
    datetime.strptime(save['created_at'], '%Y-%m-%d %H:%M:%S')
    datetime.strptime(save['last_played_at'], '%Y-%m-%d %H:%M:%S')


def test_taken_slot_and_overwrite_clears_memo(api_client):
    client, _, _ = api_client
    original = create_save(client).json()
    client.put(f"{BASE}/saves/{original['save_id']}/memo", json={'memo': 'old note'})
    assert_error(create_save(client), 409, 'STATE_CONFLICT')
    replacement = create_save(client, overwrite=True)
    assert replacement.status_code == 201
    assert replacement.json()['save_id'] != original['save_id']
    state = client.get(f"{BASE}/saves/{replacement.json()['save_id']}").json()
    assert state['day'] == state['current_day'] == 1
    assert state['memo'] == ''


def test_concurrent_slot_insert_maps_duplicate_to_conflict(api_client):
    client, _, _ = api_client
    create_save(client)

    class CursorProxy:
        def __init__(self, cursor):
            self.cursor = cursor
            self.skip_fetch = False

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self.cursor.close()

        def execute(self, query, args=None):
            if query.startswith('SELECT save_id FROM saves WHERE user_id = %s AND slot_no = %s FOR UPDATE'):
                self.skip_fetch = True
                return 0
            return self.cursor.execute(query, args)

        def fetchone(self):
            if self.skip_fetch:
                self.skip_fetch = False
                return None
            return self.cursor.fetchone()

        def __getattr__(self, name):
            return getattr(self.cursor, name)

    class ConnectionProxy:
        def __init__(self, conn):
            self.conn = conn

        def cursor(self):
            return CursorProxy(self.conn.cursor())

    def fake_db():
        conn = connect_db()
        try:
            yield ConnectionProxy(conn)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    app.dependency_overrides[get_db] = fake_db
    try:
        response = create_save(client)
    finally:
        app.dependency_overrides.pop(get_db, None)
    assert_error(response, 409, 'STATE_CONFLICT')
    assert response.json()['error']['message'] == '이미 기록이 있는 슬롯입니다.'


def test_invalid_slot_and_role_have_error_shape(api_client):
    client, _, _ = api_client
    assert_error(create_save(client, slot_no=4), 422, 'VALIDATION_ERROR')
    assert_error(create_save(client, role='admin'), 422, 'VALIDATION_ERROR')


def test_other_users_save_is_not_found_for_all_routes(api_client):
    client, use_user, _ = api_client
    save = create_save(client).json()
    use_user(1)
    assert_error(client.get(f"{BASE}/saves/{save['save_id']}"), 404, 'NOT_FOUND')
    assert_error(client.put(f"{BASE}/saves/{save['save_id']}/memo", json={'memo': 'x'}), 404, 'NOT_FOUND')
    assert_error(client.post(f"{BASE}/saves/{save['save_id']}/advance-day", json={'client_request_id': 'hidden'}), 404, 'NOT_FOUND')


def test_memo_save_and_read_back(api_client):
    client, _, _ = api_client
    save = create_save(client).json()
    memo_response = client.put(f"{BASE}/saves/{save['save_id']}/memo", json={'memo': '수첩 내용'})
    assert memo_response.status_code == 200
    assert memo_response.json()['memo'] == '수첩 내용'
    datetime.strptime(memo_response.json()['updated_at'], '%Y-%m-%d %H:%M:%S')
    assert client.get(f"{BASE}/saves/{save['save_id']}").json()['memo'] == '수첩 내용'


def test_memo_limit(api_client):
    client, _, _ = api_client
    save = create_save(client).json()
    response = client.put(f"{BASE}/saves/{save['save_id']}/memo", json={'memo': 'x' * 5001})
    assert_error(response, 422, 'VALIDATION_ERROR')
    assert response.json()['error']['message'] == '메모는 5000자까지 쓸 수 있습니다.'


def test_advance_day_is_idempotent(api_client):
    client, _, _ = api_client
    save = create_save(client).json()
    path = f"{BASE}/saves/{save['save_id']}/advance-day"
    body = {'client_request_id': 'same-request'}
    first = client.post(path, json=body)
    second = client.post(path, json=body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json()
    assert first.json()['game_state']['current_day'] == 2


@pytest.mark.parametrize('request_id', ['요청-1', 'a b'])
def test_advance_request_id_must_be_printable_ascii(api_client, request_id):
    client, _, _ = api_client
    save = create_save(client).json()
    response = client.post(
        f"{BASE}/saves/{save['save_id']}/advance-day",
        json={'client_request_id': request_id},
    )
    assert_error(response, 422, 'VALIDATION_ERROR')


def test_day_six_cannot_advance(api_client):
    client, _, user_ids = api_client
    save = create_save(client).json()
    conn = connect_db()
    with conn.cursor() as cursor:
        cursor.execute('UPDATE saves SET day = 6 WHERE save_id = %s AND user_id = %s', (save['save_id'], user_ids[0]))
    conn.commit()
    conn.close()
    response = client.post(f"{BASE}/saves/{save['save_id']}/advance-day", json={'client_request_id': 'day-six'})
    assert_error(response, 409, 'STATE_CONFLICT')
    assert response.json()['error']['message'] == '마지막 Day입니다.'


def test_unknown_route_and_origin_policy(api_client):
    client, _, _ = api_client
    assert_error(client.get(f'{BASE}/not-a-route'), 404, 'NOT_FOUND')
    bad_origin = create_save(client, slot_no=2, headers={'Origin': 'https://invalid.example'})
    assert_error(bad_origin, 403, 'ACCESS_DENIED')
    allowed_origin = 'http://localhost:8010'
    allowed = create_save(client, slot_no=2, headers={'Origin': allowed_origin})
    assert allowed.status_code == 201
    assert allowed.headers['access-control-allow-origin'] == allowed_origin
    assert allowed.headers['access-control-allow-credentials'] == 'true'
