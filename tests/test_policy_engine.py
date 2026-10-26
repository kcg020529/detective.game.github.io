import copy
from dataclasses import replace
import unittest

from backend.policy.engine import PolicyContext, decide, project
from backend.policy.repository import PolicyDenied, PolicyRepository, PolicyUnavailable
from database.loaders.load_mariadb import ROOT, load_sources


def record(kind='Action', test_id=1):
    value = dict(dataset='game-data', record_id=f'T{test_id:02d}-{kind.lower()}-001',
                 record_type=kind, test_id=test_id, day=(test_id - 1) // 5 + 1,
                 involved_ai=['YB-1'], location_ids=['중앙홀'], summary='공개 요약',
                 content='원문 전용 CANARY_BODY', allowed_roles=['prof', 'grad', 'std'])
    if kind == 'Action':
        value['witness_ai'] = ['YB-2']
    if kind == 'Dialogue':
        value['overheard_ai'] = ['YB-2']
    return value


def permission(value, role='std', level='summary'):
    return dict(dataset=value['dataset'], record_id=value['record_id'], role=role,
                disclosure_level=level)


CONTEXT = PolicyContext(1, 10, 1, 'std', 1, 'YB-1', 'game-data')


class EngineTests(unittest.TestCase):
    def test_full_approved_matrix(self):
        matrix = {
            'Setup': ('full', 'full', 'full'),
            'Action': ('summary', 'summary', 'full'),
            'Dialogue': ('metadata', 'summary', 'full'),
            'Thought': ('deny', 'deny', 'summary'),
            'Result': ('summary', 'full', 'full'),
            'Incident': ('deny', 'metadata', 'summary'),
        }
        for kind, levels in matrix.items():
            for role, level in zip(('std', 'grad', 'prof'), levels):
                with self.subTest(kind=kind, role=role):
                    value = record(kind)
                    safe = project(replace(CONTEXT, role=role), value,
                                   permission(value, role, level))
                    if level == 'deny':
                        self.assertIsNone(safe)
                    else:
                        self.assertEqual('content' in safe, level == 'full')
                        self.assertEqual('summary' in safe, level in ('summary', 'full'))
                        self.assertNotIn('allowed_roles', safe)
                        self.assertNotIn('dataset', safe)

    def test_summary_does_not_include_body_and_projection_is_a_copy(self):
        value = record()
        value['secret_internal_field'] = 'DO_NOT_EXPOSE'
        safe = project(CONTEXT, value, permission(value))
        self.assertNotIn('CANARY_BODY', str(safe))
        self.assertNotIn('secret_internal_field', safe)
        safe['involved_ai'].append('YB-6')
        self.assertEqual(value['involved_ai'], ['YB-1'])

    def test_actor_witness_and_overhearer_know_only_their_records(self):
        for kind in ('Action', 'Dialogue'):
            value = record(kind)
            self.assertTrue(decide(replace(CONTEXT, character_id='YB-2'), value,
                                   permission(value)).allowed)
            self.assertFalse(decide(replace(CONTEXT, character_id='YB-3'), value,
                                    permission(value)).allowed)

    def test_thought_and_system_incident_only_involved_ai(self):
        for kind in ('Thought', 'Incident', 'Setup', 'Result'):
            value = record(kind)
            context = replace(CONTEXT, role='prof')
            self.assertTrue(decide(context, value, permission(value, 'prof')).allowed)
            self.assertFalse(decide(replace(context, character_id='YB-2'), value,
                                    permission(value, 'prof')).allowed)

    def test_prof_cannot_bypass_day_scope_or_save(self):
        value = record(test_id=6)
        context = replace(CONTEXT, role='prof')
        self.assertEqual(decide(context, value, permission(value, 'prof', 'full')).reason,
                         'FUTURE_DAY')
        value = record()
        self.assertFalse(decide(replace(context, owner_user_id=2), value,
                                permission(value, 'prof', 'full')).allowed)
        self.assertFalse(decide(replace(context, character_id='YB-6'), value,
                                permission(value, 'prof', 'full')).allowed)

    def test_permission_row_is_required_and_bound_to_exact_key_role(self):
        value = record()
        self.assertFalse(decide(CONTEXT, value, None).allowed)
        for changes in ({'role': 'prof'}, {'dataset': 'test-data'},
                        {'record_id': 'T01-action-002'}, {'disclosure_level': 'basic_metadata'},
                        {'disclosure_level': 'deny'}, {'disclosure_level': ['full']}):
            with self.subTest(changes=changes):
                self.assertIsNone(project(CONTEXT, value, {**permission(value), **changes}))

    def test_malformed_or_missing_security_metadata_is_denied(self):
        cases = ({'witness_ai': None}, {'witness_ai': ['YB-1']}, {'involved_ai': []},
                 {'location_ids': ['unknown']}, {'day': True}, {'record_type': 'Other'},
                 {'dataset': 'test-data'}, {'record_id': 'T01-action-000'},
                 {'owner_save_id': 10}, {'overheard_ai': []})
        for changes in cases:
            value = {**record(), **changes}
            with self.subTest(changes=changes):
                self.assertFalse(decide(CONTEXT, value, permission(value)).allowed)
        value = record()
        del value['witness_ai']
        self.assertFalse(decide(CONTEXT, value, permission(value)).allowed)

    def test_invalid_context_never_grants_access(self):
        value = record()
        for changes in ({'user_id': True}, {'role': 'admin'}, {'day': 7},
                        {'character_id': 'YB-9'}, {'save_id': 0}):
            self.assertFalse(decide(replace(CONTEXT, **changes), value,
                                    permission(value)).allowed)

    def test_missing_disclosed_text_cannot_be_returned(self):
        value = record()
        value['summary'] = ''
        self.assertIsNone(project(CONTEXT, value, permission(value)))

    def test_current_game_corpus_preserves_role_and_character_boundaries(self):
        records, _, _ = load_sources(ROOT / 'data/game-data', 'game-data')
        for raw in records:
            value = {**raw, 'dataset': 'game-data'}
            known = set(raw['involved_ai']) | set(raw.get('witness_ai', [])) | set(raw.get('overheard_ai', []))
            for role, level in raw['role_permissions'].items():
                for character in (f'YB-{number}' for number in range(1, 7)):
                    with self.subTest(record_id=raw['record_id'], role=role, character=character):
                        context = replace(CONTEXT, role=role, day=6, character_id=character)
                        safe = project(context, value, permission(value, role, level))
                        self.assertEqual(safe is not None, level != 'deny' and character in known)
                        if safe is not None:
                            self.assertEqual('content' in safe, level == 'full')
                            self.assertEqual('summary' in safe, level in ('full', 'summary'))


class Cursor:
    def __init__(self, connection):
        self.connection = connection
        self.rows = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params):
        connection = self.connection
        connection.calls.append((sql, params))
        if connection.fail:
            raise RuntimeError('DB error containing private data')
        if 'FROM saves ' in sql:
            self.rows = [connection.save] if (params[0], params[1]) == (1, 10) else []
        elif 'LEFT JOIN document_permissions' in sql:
            self.rows = [{**{key: connection.record[key] for key in
                            ('dataset', 'record_id', 'record_type', 'test_id', 'day')},
                          'permission_role': connection.save['role'],
                          'disclosure_level': connection.level}]
        elif 'FROM game_record_ai ' in sql:
            self.rows = [dict(record_id=connection.record['record_id'],
                              record_type=connection.record['record_type'],
                              ai_id='YB-1', relation_kind='involved')]
        elif 'FROM game_record_locations ' in sql:
            self.rows = [dict(record_id=connection.record['record_id'], location_id='중앙홀')]
        elif sql.startswith('SELECT summary'):
            # Even an unexpectedly broad driver row is filtered before returning.
            self.rows = [dict(summary=connection.record['summary'],
                              content=connection.record['content'])]
        else:
            raise AssertionError(sql)

    def fetchone(self):
        return copy.deepcopy(self.rows[0]) if self.rows else None

    def fetchall(self):
        return copy.deepcopy(self.rows)


class Connection:
    def __init__(self):
        self.calls = []
        self.save = dict(user_id=1, save_id=10, role='std', day=1)
        self.record = record()
        self.level = 'summary'
        self.fail = False

    def cursor(self):
        return Cursor(self)


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.connection = Connection()
        self.repository = PolicyRepository(self.connection)
        self.args = dict(user_id=1, save_id=10, character_id='YB-1')

    def test_search_scope_never_fetches_summary_or_body(self):
        scope = self.repository.search_scope(**self.args)
        self.assertEqual(scope.record_ids, ('T01-action-001',))
        self.assertEqual(scope.disclosures, (('T01-action-001', 'summary'),))
        self.assertTrue(all('content' not in sql and 'summary' not in sql
                            for sql, _ in self.connection.calls))

    def test_resolve_revalidates_and_queries_only_allowed_columns(self):
        safe = self.repository.resolve(**self.args, record_ids=['T01-action-001'])
        self.assertEqual(safe[0]['summary'], '공개 요약')
        self.assertNotIn('content', safe[0])
        self.assertTrue(any(sql.startswith('SELECT summary FROM')
                            for sql, _ in self.connection.calls))
        self.assertTrue(all('SELECT summary, content' not in sql
                            for sql, _ in self.connection.calls))

    def test_retrieval_scope_is_not_authority_after_policy_changes(self):
        self.assertTrue(self.repository.search_scope(**self.args).record_ids)
        self.connection.level = 'deny'
        self.assertEqual(self.repository.resolve(**self.args, record_ids=['T01-action-001']), [])

    def test_empty_scope_missing_permission_future_day_and_wrong_ai(self):
        for level, value, character in ((None, record(), 'YB-1'),
                                        ('summary', record(test_id=6), 'YB-1'),
                                        ('summary', record(), 'YB-3')):
            self.connection.level = level
            self.connection.record = value
            args = {**self.args, 'character_id': character}
            self.assertEqual(self.repository.search_scope(**args).record_ids, ())
            self.assertEqual(self.repository.resolve(**args, record_ids=[value['record_id']]), [])

    def test_other_user_save_is_denied_before_record_lookup(self):
        with self.assertRaises(PolicyDenied):
            self.repository.search_scope(**{**self.args, 'user_id': 2})
        self.assertEqual(len(self.connection.calls), 1)

    def test_lookup_error_is_not_a_broad_search_or_partial_response(self):
        self.connection.fail = True
        with self.assertRaises(PolicyUnavailable) as error:
            self.repository.search_scope(**self.args)
        self.assertNotIn('private data', str(error.exception))
        self.assertEqual(len(self.connection.calls), 1)

    def test_empty_candidates_still_require_save_ownership(self):
        self.assertEqual(self.repository.resolve(**self.args, record_ids=[]), [])
        with self.assertRaises(PolicyDenied):
            self.repository.resolve(**{**self.args, 'user_id': 2}, record_ids=[])

    def test_metadata_does_not_fetch_text_and_full_fetches_both_fields(self):
        self.connection.level = 'metadata'
        safe = self.repository.resolve(**self.args, record_ids=['T01-action-001'])
        self.assertNotIn('summary', safe[0])
        self.assertTrue(all(not sql.startswith('SELECT summary')
                            for sql, _ in self.connection.calls))
        self.connection.level = 'full'
        safe = self.repository.resolve(**self.args, record_ids=['T01-action-001'])
        self.assertEqual(safe[0]['content'], '원문 전용 CANARY_BODY')
        self.assertTrue(any(sql.startswith('SELECT summary, content FROM')
                            for sql, _ in self.connection.calls))

    def test_candidate_ids_are_parameterized_and_not_authorization(self):
        candidate = "x' OR 1=1 --"
        self.assertEqual(self.repository.resolve(**self.args, record_ids=[candidate]), [])
        self.assertTrue(all(candidate not in sql for sql, _ in self.connection.calls))
        with self.assertRaises(PolicyDenied):
            self.repository.resolve(**self.args, record_ids=['x'] * 101)


if __name__ == '__main__':
    unittest.main()
