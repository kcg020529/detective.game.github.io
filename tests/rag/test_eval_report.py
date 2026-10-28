import json

from types import SimpleNamespace

from backend.policy.repository import PolicyDenied
from backend.rag import search
from experiments.rag import run_eval


def _row(category, variant, *, answerable=True, rank=1):
    return {
        'id': f'{category}-{variant}', 'category': category, 'variant': variant,
        'role': 'grad', 'day': 3, 'question': 'q', 'gold_ids': ['gold'] if answerable else [],
        'gold_visible': ['gold'] if answerable else [], 'rank_first_gold': rank if answerable else None,
        'returned_ids': ['gold'] if answerable else [], 'signal': 'ok', 'latency_ms': 2.0,
    }


def test_report_build_and_write_covers_variants_categories_and_violation(tmp_path):
    categories = ('guard', 'incident', 'move', 'move_day', 'place', 'place_day', 'result', 'talk', 'talk_day')
    rows = [_row(category, 'filtered', answerable=category != 'guard') for category in categories]
    rows.extend(_row('move_day', variant) for variant in ('broad', 'plain'))
    violations = [{'case_id': 'guard-plain', 'kind': 'outside_allowed_ids'}]
    cases = [{'category': row['category'], 'question': row['question']} for row in rows]
    report = run_eval.build_report(rows, violations, [], cases, 'offline',
                                   {'qdrant_url': 'memory', 'text_mode': 'header'})
    output = run_eval.write_report(report, tmp_path / 'reports' / 'offline.json')
    written = json.loads(output.read_text(encoding='utf-8'))

    assert output.is_file()
    assert written['case_count'] == len(cases)
    assert written['overall']['n_unanswerable'] == 1
    assert written['anomalies'] == []
    assert len(written['acl_violations']) == 1
    assert [entry['variant'] for entry in written['metrics'] if entry['category'] == 'move_day'] == [
        'filtered', 'broad', 'plain']


def test_extra_metrics_compute_twin_type_noise_and_offtopic_rates(monkeypatch):
    rows = [
        {**_row('twin', 'twin', rank=2), 'id': 'twin-1', 'top_summary': 'same', 'gold_summaries': ['same']},
        {**_row('mixed_type', 'mixed_type'), 'id': 'mixed-1', 'top_record_type': 'Action',
         'gold_record_types': ['Thought']},
        {**_row('move', 'plain'), 'id': 'clean-1', 'rank_first_gold': 1},
        {**_row('noisy', 'noisy'), 'id': 'noisy-1', 'clean_id': 'clean-1', 'rank_first_gold': None,
         'returned_ids': []},
        {**_row('offtopic', 'offtopic', answerable=False), 'id': 'offtopic-1', 'returned_ids': ['unrelated']},
        {**_row('offtopic', 'offtopic', answerable=False), 'id': 'offtopic-2', 'returned_ids': []},
    ]
    report = run_eval.build_report(rows, [], [], [], 'offline', {'text_mode': 'header'})
    metrics = report['extra'][0]
    assert metrics == {
        'role': 'grad', 'twin_confusion@1': 1.0, 'type_confusion@1': 1.0,
        'noise_drop': -1.0, 'nonempty_rate': 0.5,
    }
    assert report['anomalies'] == []


def test_report_write_failure_still_prints_acl_summary(tmp_path, capsys):
    report = {
        'acl_violations': [{'kind': 'outside_allowed_ids'}],
        'leftover_eval_users': [],
        'anomalies': ['move'],
    }
    destination = tmp_path / 'is-a-directory'
    destination.mkdir()

    status = run_eval.finish_report(report, destination)

    captured = capsys.readouterr()
    assert status == 1
    assert 'results write failed:' in captured.err
    assert 'ACL violations=1;' in captured.out
    assert 'unanswerable-only categories=[\'move\']' in captured.out


def test_security_aggregation_reports_violation_leak_and_fails(tmp_path, capsys):
    rows = [
        {'id': 'attack-1', 'attack': 'impersonation', 'role': 'std', 'returned_total': 1,
         'memory_entries': 1, 'memory_leaks': 1, 'rejected': False, 'expect_error': False},
        {'id': 'attack-2', 'attack': 'bad_plan', 'role': 'grad', 'returned_total': 0,
         'memory_entries': 0, 'memory_leaks': 0, 'rejected': True, 'expect_error': True},
    ]
    violations = [{'case_id': 'attack-1', 'kind': 'outside_allowed_ids'}]
    security = run_eval._security_report(rows, violations)
    report = {'acl_violations': violations, 'leftover_eval_users': [], 'anomalies': [],
              'security': security}

    status = run_eval.finish_report(report, tmp_path / 'security.json')

    output = capsys.readouterr().out
    assert status == 1
    group = {(row['attack'], row['role']): row for row in security['by_attack_role']}
    assert group[('impersonation', 'std')]['violations'] == 1
    assert group[('impersonation', 'std')]['memory_leaks'] == 1
    assert security['unauthorized_retrieval_rate'] == 1.0
    assert security['context_delivery_rate'] == 1.0
    assert 'SECURITY: violations=1 memory_leaks=1 rejected_ok=1/1' in output


def test_cross_save_retrieve_is_rejected_by_policy_repository(monkeypatch):
    class FakeRepository:
        def __init__(self, _connection):
            pass

        def search_scope(self, **kwargs):
            assert kwargs['user_id'] == 101 and kwargs['save_id'] == 202
            raise PolicyDenied('SAVE_NOT_FOUND')

    monkeypatch.setattr(search, 'PolicyRepository', FakeRepository)
    case = {'attack': 'cross_save', 'expect_error': 'PolicyDenied', 'character_id': 'YB-2',
            'plan': {'query': 'cross save check', 'limit': 5}}

    result, rejected, error = run_eval._retrieve_attack_case(
        case, object(), user_id=101, save_id=201, foreign_save_id=202,
        qdrant=object(), embedder=SimpleNamespace(count_tokens=lambda _query: 1))

    assert result is None and rejected and error is None


def test_memory_leak_check_normalizes_body_and_only_checks_limited_levels():
    result = SimpleNamespace(
        memory=[{'id': 'm1', 'text': 'Secret   content body excerpt'},
                {'id': 'm2', 'text': 'Private summary phrase det'}],
        id_map={'m1': 'summary-record', 'm2': 'metadata-record'},
    )
    sources = {
        'summary-record': {'content': 'Secret content body excerpt continues', 'summary': 'Safe summary'},
        'metadata-record': {'content': 'Unseen body text', 'summary': 'Private summary phrase details'},
    }

    assert run_eval._memory_leaks(
        result, {'summary-record': 'summary', 'metadata-record': 'metadata', 'full-record': 'full'}, sources
    ) == (2, 2)


def test_expect_none_ids_adds_security_violation():
    case = {'id': 'attack-source', 'expect_none_of': {}, 'expect_none_ids': ['private-record']}
    returned = [{'record_id': 'private-record'}]

    issues = run_eval._violations(case, returned, {'private-record': 'full'}, {})

    assert [issue['kind'] for issue in issues] == ['forbidden_record_id']


def test_security_table_prints_every_column_without_key_errors(capsys):
    # 머리글과 데이터 키가 다른 열(returned ← returned_total)이 출력 중 KeyError를 내지 않아야 한다
    rows = [
        {'id': 'a-1', 'attack': 'dump_all', 'role': 'std', 'returned_ids': ['x', 'y'], 'returned_total': 2,
         'memory_entries': 2, 'memory_leaks': 0, 'rejected': False, 'expect_error': False},
        {'id': 'a-2', 'attack': 'bad_plan', 'role': 'std', 'returned_ids': [], 'returned_total': 0,
         'memory_entries': 0, 'memory_leaks': 0, 'rejected': True, 'expect_error': True},
    ]

    run_eval._print_security_table(run_eval._security_report(rows, []))

    out = capsys.readouterr().out
    assert 'dump_all | std | 1 | 2 | 0 | 0 | 0' in out
    assert 'bad_plan | std | 1 | 0 | 0 | 0 | 1' in out
    assert 'unauthorized retrieval rate=0.000000' in out
