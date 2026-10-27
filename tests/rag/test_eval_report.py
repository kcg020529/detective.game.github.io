import json

from experiments.rag import run_eval


def _row(category, variant, *, answerable=True, rank=1):
    return {
        'id': f'{category}-{variant}', 'category': category, 'variant': variant,
        'role': 'grad', 'day': 3, 'question': 'q', 'gold_ids': ['gold'] if answerable else [],
        'gold_visible': ['gold'] if answerable else [], 'rank_first_gold': rank if answerable else None,
        'returned_ids': ['gold'] if answerable else [], 'signal': 'ok', 'latency_ms': 2.0,
    }


def test_report_build_and_write_covers_variants_categories_and_violation(tmp_path, monkeypatch):
    categories = ('guard', 'incident', 'move', 'move_day', 'place', 'place_day', 'result', 'talk', 'talk_day')
    rows = [_row(category, 'filtered', answerable=category != 'guard') for category in categories]
    rows.extend(_row('move_day', variant) for variant in ('broad', 'plain'))
    violations = [{'case_id': 'guard-plain', 'kind': 'outside_allowed_ids'}]
    cases = [{'category': row['category'], 'question': row['question']} for row in rows]
    monkeypatch.setattr(run_eval, '_config', lambda url, mode: {'qdrant_url': url, 'text_mode': mode})

    report = run_eval.build_report(rows, violations, [], cases, 'offline', 'memory', 'header')
    output = run_eval.write_report(report, tmp_path / 'reports' / 'offline.json')
    written = json.loads(output.read_text(encoding='utf-8'))

    assert output.is_file()
    assert written['case_count'] == len(cases)
    assert written['overall']['n_unanswerable'] == 1
    assert written['anomalies'] == []
    assert len(written['acl_violations']) == 1
    assert [entry['variant'] for entry in written['metrics'] if entry['category'] == 'move_day'] == [
        'filtered', 'broad', 'plain']


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
