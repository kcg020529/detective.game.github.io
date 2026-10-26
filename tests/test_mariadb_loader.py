import copy
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('load_mariadb', ROOT / 'database/loaders/load_mariadb.py')
loader = importlib.util.module_from_spec(spec)
spec.loader.exec_module(loader)


class Cursor:
    def __init__(self, fail=False):
        self.fail = fail
        self.calls = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        self.calls.append((sql, params))
        if self.fail and sql.startswith('INSERT INTO game_record_ai'):
            raise RuntimeError('simulated child insert failure')

    def executemany(self, sql, params):
        for row in params:
            self.execute(sql, row)

    def fetchall(self):
        return [(loc,) for loc in loader.LOCATIONS]


class Connection:
    def __init__(self, fail=False):
        self.cur = Cursor(fail)
        self.commits = self.rollbacks = self.begins = 0

    def cursor(self):
        return self.cur

    def begin(self):
        self.begins += 1

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class LoaderTests(unittest.TestCase):
    def setUp(self):
        self.record = {
            'record_id': 'T01-action-001', 'record_type': 'Action', 'test_id': 1, 'day': 1,
            'involved_ai': ['YB-1'], 'witness_ai': ['YB-2'], 'location_ids': ['중앙홀'],
            'summary': '행동 요약', 'content': "따옴표 ' 와 SQL ; 을 포함한 본문",
            'allowed_roles': ['std'],
            'role_permissions': {'std': 'metadata', 'grad': 'deny', 'prof': 'deny'},
        }

    def test_permission_is_never_implicitly_granted(self):
        del self.record['role_permissions']
        with self.assertRaises(loader.ValidationError):
            loader.validate_record(self.record, 'test-data')
        permissions = loader.validate_record(self.record, 'test-data', 'summary')['role_permissions']
        self.assertEqual(permissions, {'std': 'summary', 'grad': 'deny', 'prof': 'deny'})

    def test_missing_locations_requires_explicit_compatibility(self):
        del self.record['location_ids']
        with self.assertRaises(loader.ValidationError):
            loader.validate_record(self.record, 'test-data')
        self.assertEqual(loader.validate_record(self.record, 'test-data', allow_missing_locations=True)['location_ids'], [])

    def test_invalid_security_metadata_rejected(self):
        for field, value in [('allowed_roles', ['admin']), ('involved_ai', ['YB-9']),
                             ('location_ids', ['없는 장소']), ('role_permissions', {'std': 'open'}),
                             ('witness_ai', ['YB-1']), ('test_id', True)]:
            with self.subTest(field=field):
                record = copy.deepcopy(self.record)
                record[field] = value
                with self.assertRaises(loader.ValidationError):
                    loader.validate_record(record, 'game-data')

    def test_wrong_id_type_or_day_rejected(self):
        for field, value in [('record_id', 'T02-action-001'), ('day', 2),
                             ('record_id', 'T01-action-000'), ('record_type', 'Result')]:
            record = copy.deepcopy(self.record)
            record[field] = value
            with self.assertRaises(loader.ValidationError):
                loader.validate_record(record, 'game-data')

    def test_missing_witness_field_rejected(self):
        del self.record['witness_ai']
        with self.assertRaises(loader.ValidationError):
            loader.validate_record(self.record, 'game-data')

    def test_duplicate_ids_rejected_before_db(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)
            (path / 'records.json').write_text(json.dumps([self.record, self.record]), encoding='utf-8')
            with self.assertRaises(loader.ValidationError):
                loader.load_sources(path, 'test-data')

    def test_json_duplicate_keys_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'records.json'
            path.write_text('{"day":1,"day":2}', encoding='utf-8')
            with self.assertRaises(loader.ValidationError):
                loader.read_json(path)

    def test_existing_game_sources_validate(self):
        records, rules, missing = loader.load_sources(ROOT / 'data/game-data', 'game-data')
        self.assertGreater(len(records), 0)
        self.assertEqual(rules['rule_id'], 'GAME_RULES_V1')
        self.assertEqual(missing, 0)

    def test_approved_policy_for_all_six_types_and_three_roles(self):
        expected = {
            'Setup': {'std': 'full', 'grad': 'full', 'prof': 'full'},
            'Action': {'std': 'summary', 'grad': 'summary', 'prof': 'full'},
            'Dialogue': {'std': 'metadata', 'grad': 'summary', 'prof': 'full'},
            'Thought': {'std': 'deny', 'grad': 'deny', 'prof': 'summary'},
            'Result': {'std': 'summary', 'grad': 'full', 'prof': 'full'},
            'Incident': {'std': 'deny', 'grad': 'metadata', 'prof': 'summary'},
        }
        self.assertEqual(loader.load_disclosure_policy(), expected)
        records, _, _ = loader.load_sources(ROOT / 'data/game-data', 'game-data')
        for record in records:
            with self.subTest(record_id=record['record_id']):
                self.assertEqual(record['role_permissions'], expected[record['record_type']])
                self.assertEqual(set(record['allowed_roles']),
                                 {role for role, level in expected[record['record_type']].items()
                                  if level != 'deny'})

    def test_game_policy_does_not_use_legacy_roles_or_single_default(self):
        record = copy.deepcopy(self.record)
        del record['role_permissions']
        record['allowed_roles'] = []
        self.assertEqual(loader.validate_record(record, 'game-data')['role_permissions'],
                         {'std': 'summary', 'grad': 'summary', 'prof': 'full'})
        with self.assertRaises(loader.ValidationError):
            loader.validate_record(record, 'game-data', 'full')
        record['disclosure_level'] = 'full'
        with self.assertRaises(loader.ValidationError):
            loader.validate_record(record, 'game-data')

    def test_explicit_partial_map_denies_missing_roles(self):
        self.record['role_permissions'] = {'grad': 'summary'}
        self.record['allowed_roles'] = ['prof', 'grad', 'std']
        self.assertEqual(loader.validate_record(self.record, 'game-data')['role_permissions'],
                         {'std': 'deny', 'grad': 'summary', 'prof': 'deny'})

    def test_invalid_permission_maps_and_removed_level_rejected(self):
        for value in (None, [], {'admin': 'full'}, {'std': 'basic_metadata'}, {'std': 1}):
            with self.subTest(value=value):
                record = copy.deepcopy(self.record)
                record['role_permissions'] = value
                with self.assertRaises(loader.ValidationError):
                    loader.validate_record(record, 'game-data')
        del self.record['role_permissions']
        self.record['disclosure_level'] = 'basic_metadata'
        with self.assertRaises(loader.ValidationError):
            loader.validate_record(self.record, 'test-data')

    def test_incomplete_policy_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'policy.json'
            policy = loader.load_disclosure_policy()
            del policy['Incident']['std']
            path.write_text(json.dumps(policy), encoding='utf-8')
            with self.assertRaises(loader.ValidationError):
                loader.load_disclosure_policy(path)
            del policy['Incident']
            path.write_text(json.dumps(policy), encoding='utf-8')
            with self.assertRaises(loader.ValidationError):
                loader.load_disclosure_policy(path)

    def test_invalid_permissions_rejected_before_writes(self):
        del self.record['role_permissions']['prof']
        connection = Connection()
        with self.assertRaises(loader.ValidationError):
            loader.import_records(connection, 'test-data', [self.record])
        self.assertEqual(connection.begins, 0)
        self.assertEqual(connection.cur.calls, [])

    def test_each_record_writes_three_separate_permissions(self):
        connection = Connection()
        loader.import_records(connection, 'test-data', [self.record])
        inserted = [params for sql, params in connection.cur.calls
                    if sql.startswith('INSERT INTO document_permissions ')]
        self.assertEqual(set(inserted), {
            ('test-data', 'T01-action-001', 'std', 'metadata'),
            ('test-data', 'T01-action-001', 'grad', 'deny'),
            ('test-data', 'T01-action-001', 'prof', 'deny'),
        })

    def test_nonfinite_json_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'rules.json'
            path.write_text('{"score":NaN}', encoding='utf-8')
            with self.assertRaises(loader.ValidationError):
                loader.read_json(path)

    def test_test_sources_use_explicit_legacy_mode(self):
        with self.assertRaises(loader.ValidationError):
            loader.load_sources(ROOT / 'data/test-data', 'test-data', 'full')
        records, rules, missing = loader.load_sources(ROOT / 'data/test-data', 'test-data', 'full', True)
        self.assertGreater(len(records), 0)
        self.assertGreater(missing, 0)
        self.assertIsNone(rules)

    def test_commit_and_parameterized_body(self):
        connection = Connection()
        loader.import_records(connection, 'test-data', [self.record])
        self.assertEqual((connection.begins, connection.commits, connection.rollbacks), (1, 1, 0))
        inserts = [(sql, params) for sql, params in connection.cur.calls if sql.startswith('INSERT INTO game_records ')]
        self.assertEqual(len(inserts), 1)
        self.assertNotIn(self.record['content'], inserts[0][0])
        self.assertIn(self.record['content'], inserts[0][1])

    def test_child_failure_rolls_back_entire_batch(self):
        connection = Connection(fail=True)
        with self.assertRaises(RuntimeError):
            loader.import_records(connection, 'test-data', [self.record])
        self.assertEqual((connection.commits, connection.rollbacks), (0, 1))

    def test_shared_rules_are_imported(self):
        rules = loader.validate_rules(loader.read_json(ROOT / 'data/game-data/rules.json'))
        connection = Connection()
        loader.import_records(connection, 'game-data', [], rules)
        self.assertTrue(any(sql.startswith('INSERT INTO game_rules ') for sql, _ in connection.cur.calls))


if __name__ == '__main__':
    unittest.main()
