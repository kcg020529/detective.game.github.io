import os
import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pymysql.err import InterfaceError, OperationalError

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / 'infrastructure' / 'docker' / '.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))

from backend.api.current_user import current_user_id
from backend.api.db import connect_db
from backend.api.main import app


@pytest.fixture(scope='session', autouse=True)
def database_available():
    if os.getenv('KERVION_OFFLINE_TESTS') == '1':
        pytest.skip('Offline run: live MariaDB tests are disabled')
    try:
        conn = connect_db()
        conn.close()
    except (OperationalError, InterfaceError) as exc:
        pytest.skip(f'Local MariaDB is unavailable: {exc.args[0]}')


@pytest.fixture
def api_client(database_available):
    username_tag = secrets.token_hex(6)
    conn = connect_db()
    user_ids = []
    with conn.cursor() as cursor:
        for suffix in ('a', 'b'):
            cursor.execute(
                'INSERT INTO users (username, password_hash) VALUES (%s, %s)',
                (f'test_{username_tag}_{suffix}', '!'),
            )
            user_ids.append(cursor.lastrowid)
    conn.commit()
    conn.close()

    active = {'user_id': user_ids[0]}
    app.dependency_overrides[current_user_id] = lambda: active['user_id']
    client = TestClient(app)
    yield client, lambda index: active.update(user_id=user_ids[index]), user_ids
    client.close()
    app.dependency_overrides.clear()

    conn = connect_db()
    with conn.cursor() as cursor:
        cursor.execute('DELETE FROM saves WHERE user_id IN (%s, %s)', tuple(user_ids))
        cursor.execute('DELETE FROM users WHERE user_id IN (%s, %s)', tuple(user_ids))
    conn.commit()
    conn.close()
