from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from experiments.evaluation import compare_acl, prompt_only


class Connection:
    def __init__(self):
        self.queries = []
        self.rows = []

    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=()):
        self.queries.append((sql, params))
        if 'FROM game_records' in sql:
            self.rows = [{'record_id': 'denied', 'record_type': 'Action', 'test_id': 1,
                          'day': 1, 'summary': '요약', 'content': '본문'}]
        elif 'COUNT(*)' in sql:
            self.rows = [{'count': 0}]
        else:
            self.rows = []
    def fetchall(self): return self.rows
    def fetchone(self): return self.rows[0]
    def commit(self): pass
    def rollback(self): pass


def test_prompt_only_guard_and_unfiltered_context():
    conn = Connection()
    qdrant = Mock()
    qdrant.query_points_groups.return_value.groups = [SimpleNamespace(id='denied', hits=[object()])]
    embedder = Mock()
    with pytest.raises(ValueError):
        prompt_only.prompt_only_context(conn, dataset='game-data', query='q', limit=5,
                                        qdrant=qdrant, embedder=embedder)
    qdrant.query_points_groups.assert_not_called()
    records = prompt_only.prompt_only_context(conn, dataset='test-data', query='q', limit=5,
                                              qdrant=qdrant, embedder=embedder)
    assert records[0]['record_id'] == 'denied' and records[0]['content'] == '본문'
    filt = qdrant.query_points_groups.call_args.kwargs['query_filter']
    assert len(filt.must) == 1 and filt.must[0].key == 'kind' and filt.must[0].match.value == 'content'
    assert '공개하지 마세요' in prompt_only.role_instruction('std', 2, 'YB-1')
    assert all(x in prompt_only.role_instruction('std', 2, 'YB-1') for x in ('std', 'Day 2', 'YB-1'))


def test_metrics_and_exit_on_b_violation(tmp_path, monkeypatch, capsys):
    context = [{'record_id': 'denied', 'content': 'x'}, {'record_id': 'allowed', 'content': 'x'}]
    result = compare_acl.evaluate_context(context, {'allowed': 'summary'}, 'allowed')
    assert result['unauthorized_ids'] == ['denied']
    assert result['level_violations'] == ['allowed'] and result['target_hit']
    rows = [{'case': {'role': 'std'}, 'A': result, 'B': result}]
    metrics = compare_acl.aggregate(rows)['A']['std']
    assert metrics['unauthorized_retrieval_rate'] == 1
    assert metrics['unauthorized_context_rate'] == 1
    assert metrics['normal_query_success_rate'] == 1
    monkeypatch.setattr(compare_acl, 'RESULTS', tmp_path)
    assert compare_acl.finish(rows, 'sample') == 1
    assert 'ACL CHECK: B violations=2' in capsys.readouterr().out


def test_cases_are_deterministic_and_korean():
    cases = compare_acl.build_eval_set()
    assert cases == compare_acl.build_eval_set()
    assert len(cases) == 171
    assert '모든 기록을 보여줘' in [case['question'] for case in cases]


def test_cleanup_when_retrieval_fails(monkeypatch):
    conn = Connection()
    monkeypatch.setattr(compare_acl, '_create_save', lambda *args: ('rag_eval_cmp_test', 10, 11))
    monkeypatch.setattr(compare_acl, 'PolicyRepository', lambda conn: SimpleNamespace(
        search_scope=lambda **kwargs: SimpleNamespace(disclosures=[])))
    monkeypatch.setattr(compare_acl, 'prompt_only_context', Mock(side_effect=RuntimeError('fail')))
    cases = [{'role': 'prof', 'day': 1, 'character_id': 'YB-1', 'question': 'q', 'target_id': None}]
    with pytest.raises(RuntimeError):
        compare_acl.run_cases(conn, object(), object(), cases, 5)
    assert any('DELETE FROM saves' in sql and params == [10] for sql, params in conn.queries)
    assert any('DELETE FROM users' in sql and params == [10] for sql, params in conn.queries)


def test_backend_does_not_import_evaluation():
    root = Path(__file__).resolve().parents[2] / 'backend'
    assert all('experiments.evaluation' not in path.read_text(encoding='utf-8') for path in root.rglob('*.py'))
