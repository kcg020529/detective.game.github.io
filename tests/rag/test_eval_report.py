import json

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
