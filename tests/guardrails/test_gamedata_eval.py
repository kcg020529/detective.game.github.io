from pathlib import Path

import pytest

from experiments.guardrails_rebuild.gamedata import collect, evaluate, leaks


def test_leak_builder_is_deterministic_and_labels_source_ids():
    recorded = [{'question_id': 'q1', 'draft': {'content': '정상 답변입니다.', 'response_type': 'normal'},
                 'allowed_record_ids': ['allowed'], 'records': [{'record_id': 'allowed', 'summary': '허용 요약'}],
                 'role': 'grad', 'day': 1, 'character_id': 'YB-1', 'question': '질문'}]
    catalog = [{'record_id': 'allowed', 'summary': '허용 요약', 'content': '허용된 비밀 본문 문장입니다.'},
               {'record_id': 'other', 'summary': '다른 요약 문장입니다.', 'content': '미허가 보라수정나침반 기록입니다.'}]
    first = leaks.build_leaks(recorded, {'records': catalog})
    assert first == leaks.build_leaks(recorded, catalog)
    assert {row['kind'] for row in first} == {'verbatim', 'withheld', 'blend'}
    assert all(row['leaked_record_id'] in {'allowed', 'other'} for row in first)


def test_evaluator_metrics_and_question_hash_split_are_stable():
    recorded = [{'question_id': 'question-id', 'draft': {'content': '정상입니다.', 'response_type': 'normal'},
                 'allowed_record_ids': ['r1'], 'records': [{'record_id': 'r1', 'summary': '허용'}],
                 'role': 'std', 'day': 1, 'character_id': 'YB-1', 'question': '질문'}]
    catalog = [{'record_id': 'r1', 'summary': '허용 요약입니다.', 'content': '허용 본문 문장입니다.'},
               {'record_id': 'r2', 'summary': '미허가 초록은하수 보관함입니다.',
                'content': '미허가 초록은하수 보관함에서 기록을 확인했습니다.'}]
    result = evaluate.evaluate(recorded, catalog, split='all')
    assert result['metrics']['benign_total'] == 1
    assert result['metrics']['leak_catch']['verbatim']['total'] == 1
    assert result['metrics']['leak_catch']['withheld']['total'] == 1
    assert evaluate.split_for('question-id') == evaluate.split_for('question-id')
    assert result == evaluate.evaluate(recorded, catalog, split='all')


class FakeConnection:
    def __init__(self): self.queries = []
    def cursor(self): return self
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, sql, params=()):
        self.queries.append((sql, params))
    def fetchone(self): return {'count': 0}
    def commit(self): pass
    def rollback(self): pass


def test_live_collect_cleans_temporary_user_after_exception(tmp_path):
    conn = FakeConnection()
    def fail_factory(*args): raise RuntimeError('pipeline setup failed')
    with pytest.raises(RuntimeError):
        collect.collect(conn, roles=('prof',), days=(1,), questions=[{'id': 'q', 'question': '질문'}],
                        create_save=lambda *args: ('rag_eval_guard_x', 7, 9),
                        pipeline_factory=fail_factory, output_path=tmp_path / 'drafts.json')
    assert any('DELETE FROM saves' in sql and params == [7] for sql, params in conn.queries)
    assert any('DELETE FROM users' in sql and params == [7] for sql, params in conn.queries)


def test_collector_has_real_korean_template():
    questions = collect.load_questions()
    assert any('어디로 이동했어?' in row['question'] for row in questions)
