from datetime import datetime

from backend.api.db import connect_db


BASE = '/api/v1'


def assert_error(response, status, code):
    assert response.status_code == status
    error = response.json()['error']
    assert error['code'] == code
    assert error['request_id'].startswith('req_')


def create_save(client):
    response = client.post(f'{BASE}/saves', json={'slot_no': 1, 'role': 'grad'})
    assert response.status_code == 201
    return response.json()


def insert_messages(save_id, rows):
    conn = connect_db()
    try:
        with conn.cursor() as cursor:
            cursor.executemany(
                'INSERT INTO chat_messages (save_id, ai_id, sender, content, response_type) '
                'VALUES (%s, %s, %s, %s, %s)',
                [(save_id, *row) for row in rows],
            )
            cursor.execute(
                'SELECT message_id FROM chat_messages WHERE save_id = %s AND ai_id = %s ORDER BY message_id',
                (save_id, 'YB-1'),
            )
            ids = [row['message_id'] for row in cursor.fetchall()]
        conn.commit()
        return ids
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def test_empty_channel_and_read_does_not_touch_save(api_client):
    client, _, user_ids = api_client
    save = create_save(client)
    conn = connect_db()
    with conn.cursor() as cursor:
        cursor.execute(
            'UPDATE saves SET last_played_at = DATE_SUB(NOW(), INTERVAL 1 DAY) '
            'WHERE save_id = %s AND user_id = %s',
            (save['save_id'], user_ids[0]),
        )
        cursor.execute('SELECT last_played_at FROM saves WHERE save_id = %s', (save['save_id'],))
        last_played_before = cursor.fetchone()['last_played_at'].strftime('%Y-%m-%d %H:%M:%S')
    conn.commit()
    conn.close()

    response = client.get(f"{BASE}/saves/{save['save_id']}/chats/YB-1")
    assert response.status_code == 200
    assert response.json() == {'messages': [], 'has_more': False}

    conn = connect_db()
    with conn.cursor() as cursor:
        cursor.execute('SELECT last_played_at FROM saves WHERE save_id = %s', (save['save_id'],))
        assert cursor.fetchone()['last_played_at'].strftime('%Y-%m-%d %H:%M:%S') == last_played_before
    conn.close()


def test_history_paginates_oldest_to_newest_and_filters_ai(api_client):
    client, _, _ = api_client
    save = create_save(client)
    rows = [
        ('YB-1', 'user' if index % 2 == 0 else 'ai', f'message-{index + 1}', None if index % 2 == 0 else 'normal')
        for index in range(45)
    ]
    rows.extend(('YB-2', 'ai', f'other-ai-{index}', 'normal') for index in range(3))
    ids = insert_messages(save['save_id'], rows)
    path = f"{BASE}/saves/{save['save_id']}/chats/YB-1"

    first = client.get(path)
    first_body = first.json()
    assert first.status_code == 200
    assert [row['message_id'] for row in first_body['messages']] == ids[25:45]
    assert first_body['has_more'] is True
    assert all(row['ai_id'] == 'YB-1' for row in first_body['messages'])
    assert first_body['messages'][0]['sender'] == 'ai'
    assert first_body['messages'][1]['sender'] == 'user'
    assert first_body['messages'][1]['response_type'] is None
    datetime.strptime(first_body['messages'][0]['created_at'], '%Y-%m-%d %H:%M:%S')

    second = client.get(path, params={'before': ids[25]})
    assert [row['message_id'] for row in second.json()['messages']] == ids[5:25]
    assert second.json()['has_more'] is True

    last = client.get(path, params={'before': ids[5]})
    assert [row['message_id'] for row in last.json()['messages']] == ids[:5]
    assert last.json()['has_more'] is False


def test_chat_history_requires_owned_save_and_valid_parameters(api_client):
    client, use_user, _ = api_client
    save = create_save(client)
    use_user(1)
    assert_error(client.get(f"{BASE}/saves/{save['save_id']}/chats/YB-1"), 404, 'NOT_FOUND')
    use_user(0)
    assert_error(client.get(f"{BASE}/saves/{save['save_id']}/chats/YB-7"), 422, 'VALIDATION_ERROR')
    assert_error(client.get(f"{BASE}/saves/{save['save_id']}/chats/YB-1", params={'limit': 0}), 422, 'VALIDATION_ERROR')
    assert_error(client.get(f"{BASE}/saves/{save['save_id']}/chats/YB-1", params={'limit': 51}), 422, 'VALIDATION_ERROR')
