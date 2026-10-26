import os
import secrets
from pathlib import Path

import pytest
from pymysql.err import InterfaceError, OperationalError
from qdrant_client import QdrantClient

from backend.api.db import connect_db
from backend.policy.repository import PolicyDenied, PolicyRepository
from backend.rag.embedder import VECTOR_SIZE
from backend.rag.index import index_dataset
from backend.rag.search import search_records

ROOT = Path(__file__).resolve().parents[2]
ENV_FILE = ROOT / 'infrastructure' / 'docker' / '.env'
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


class FakeEmbedder:
    def count_tokens(self, text):
        return len(text.split()) + 2

    def embed_documents(self, texts):
        return [self.embed_query(text) for text in texts]

    def embed_query(self, text):
        return [1.0] + [0.0] * (VECTOR_SIZE - 1)


@pytest.fixture(scope='module')
def database_available():
    try:
        connection = connect_db()
    except (OperationalError, InterfaceError) as exc:
        pytest.skip(f'Local MariaDB is unavailable: {exc.args[0]}')
    connection.close()


@pytest.fixture(scope='module')
def indexed_qdrant(database_available):
    connection = connect_db()
    qdrant = QdrantClient(':memory:')
    try:
        embedder = FakeEmbedder()
        index_dataset(connection, qdrant, 'game-data', embedder)
        index_dataset(connection, qdrant, 'test-data', embedder)
        yield qdrant
    finally:
        qdrant.close()
        connection.close()


@pytest.fixture
def test_saves(database_available):
    tag = secrets.token_hex(8)
    connection = connect_db()
    user_ids = []
    saves = {}
    try:
        with connection.cursor() as cursor:
            for suffix in ('a', 'b'):
                cursor.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s)',
                               (f'rag_policy_{tag}_{suffix}', '!'))
                user_ids.append(cursor.lastrowid)
            cursor.execute('INSERT INTO saves (user_id, slot_no, role, day) VALUES (%s, 1, %s, %s)',
                           (user_ids[0], 'grad', 1))
            saves['grad_day1'] = cursor.lastrowid
            cursor.execute('INSERT INTO saves (user_id, slot_no, role, day) VALUES (%s, 2, %s, %s)',
                           (user_ids[0], 'std', 6))
            saves['std_day6'] = cursor.lastrowid
            cursor.execute('INSERT INTO saves (user_id, slot_no, role, day) VALUES (%s, 1, %s, %s)',
                           (user_ids[1], 'grad', 6))
            saves['other_save'] = cursor.lastrowid
        connection.commit()
        yield {'user_id': user_ids[0], 'other_user_id': user_ids[1], **saves}
    finally:
        try:
            if user_ids:
                placeholders = ', '.join(['%s'] * len(user_ids))
                with connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM saves WHERE user_id IN ({placeholders})', tuple(user_ids))
                    cursor.execute(f'DELETE FROM users WHERE user_id IN ({placeholders})', tuple(user_ids))
                connection.commit()
        finally:
            connection.close()


class TrackingQdrant:
    def __init__(self, client):
        self.client = client
        self.calls = []
        self.groups = []

    def __getattr__(self, name):
        value = getattr(self.client, name)
        if not callable(value):
            return value

        def call(*args, **kwargs):
            self.calls.append(name)
            result = value(*args, **kwargs)
            if name == 'query_points_groups':
                self.groups = result.groups
            return result
        return call


def _search(connection, qdrant, *, user_id, save_id, character_id='YB-1', plan=None):
    return search_records(
        connection, user_id=user_id, save_id=save_id, character_id=character_id,
        dataset='game-data', plan=plan or {'query': 'record lookup', 'limit': 20},
        qdrant=qdrant, embedder=FakeEmbedder(),
    )


def test_day_one_save_never_receives_day_two_records(indexed_qdrant, test_saves):
    connection = connect_db()
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT content FROM game_records WHERE dataset='game-data' AND day=2 LIMIT 1")
            day_two_text = cursor.fetchone()['content']
        result = _search(connection, indexed_qdrant, user_id=test_saves['user_id'],
                         save_id=test_saves['grad_day1'], character_id='YB-2',
                         plan={'query': day_two_text, 'limit': 20})
        assert result
        assert all(row['day'] <= 1 for row in result)
    finally:
        connection.close()


def test_other_users_save_is_denied_before_qdrant(indexed_qdrant, test_saves):
    connection = connect_db()
    tracked = TrackingQdrant(indexed_qdrant)
    try:
        with pytest.raises(PolicyDenied):
            _search(connection, tracked, user_id=test_saves['user_id'],
                    save_id=test_saves['other_save'])
        assert tracked.calls == []
    finally:
        connection.close()


def test_ai_scope_and_foreign_thought_are_enforced(indexed_qdrant, test_saves):
    connection = connect_db()
    try:
        scope = PolicyRepository(connection).search_scope(
            user_id=test_saves['user_id'], save_id=test_saves['std_day6'],
            character_id='YB-1', dataset='game-data')
        allowed = {record_id for record_id, _ in scope.disclosures}
        result = _search(connection, indexed_qdrant, user_id=test_saves['user_id'],
                         save_id=test_saves['std_day6'], character_id='YB-1')
        assert result
        assert {row['record_id'] for row in result} <= allowed

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT r.record_id FROM game_records r JOIN game_record_ai a "
                "ON a.dataset=r.dataset AND a.record_id=r.record_id "
                "WHERE r.dataset='game-data' AND r.record_type='Thought' "
                "AND a.relation_kind='involved' AND a.ai_id <> 'YB-1' LIMIT 1")
            foreign_thought = cursor.fetchone()['record_id']
        thoughts = _search(connection, indexed_qdrant, user_id=test_saves['user_id'],
                           save_id=test_saves['std_day6'], character_id='YB-1',
                           plan={'query': foreign_thought, 'record_types': ['Thought'], 'limit': 20})
        assert foreign_thought not in {row['record_id'] for row in thoughts}
    finally:
        connection.close()


def test_game_data_search_stays_in_game_data_collection(indexed_qdrant, test_saves):
    connection = connect_db()
    tracked = TrackingQdrant(indexed_qdrant)
    try:
        result = _search(connection, tracked, user_id=test_saves['user_id'],
                         save_id=test_saves['std_day6'], character_id='YB-1')
        assert result
        assert tracked.groups
        assert all(hit.payload['dataset'] == 'game-data'
                   for group in tracked.groups for hit in group.hits)
    finally:
        connection.close()


def test_std_dialogue_returns_metadata_fields_only(indexed_qdrant, test_saves):
    connection = connect_db()
    try:
        for number in range(1, 7):
            result = _search(connection, indexed_qdrant, user_id=test_saves['user_id'],
                             save_id=test_saves['std_day6'], character_id=f'YB-{number}',
                             plan={'query': 'Dialogue', 'record_types': ['Dialogue'], 'limit': 20})
            if result:
                break
        assert result
        assert all('summary' not in row and 'content' not in row for row in result)
        assert all(row['record_type'] == 'Dialogue' for row in result)
    finally:
        connection.close()
