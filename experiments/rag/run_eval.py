"""MariaDB·Qdrant 실제 자료로 RAG 기준선을 측정한다."""

import argparse
import json
import os
import re
import secrets
import subprocess
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient

from backend.api.db import connect_db
from backend.policy.repository import PolicyDenied, PolicyRepository
from backend.rag.chunking import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
from backend.rag.embedder import FastEmbedder, MODEL_NAME
from backend.rag.errors import RagRequestError
from backend.rag.index import load_env
from backend.rag.service import retrieve
from experiments.rag.build_cases import OUTPUT as CASES_FILE, load_records

RESULTS = ROOT / 'experiments' / 'rag' / 'results'
BASE_FIELDS = {'record_id', 'record_type', 'test_id', 'day', 'location_ids', 'involved_ai'}
VARIANT_ORDER = {'filtered': 0, 'broad': 1, 'plain': 2}


def _metric_sort_key(item):
    category, role, variant = item[0]
    return category, role, VARIANT_ORDER.get(variant, len(VARIANT_ORDER))


def _git(*args):
    try:
        return subprocess.check_output(['git', *args], cwd=ROOT, text=True, stderr=subprocess.DEVNULL).strip()
    except (OSError, subprocess.CalledProcessError):
        return None


def _manifest_text_mode(qdrant):
    point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))
    points = qdrant.retrieve(collection_name='kervion_rag_manifest', ids=[point_id], with_payload=True)
    return (points[0].payload or {}).get('text_mode', 'plain') if points else 'plain'


def _config(qdrant_url, text_mode):
    return {
        'model_name': MODEL_NAME,
        'chunk_max_tokens': CHUNK_MAX_TOKENS,
        'chunk_overlap_tokens': CHUNK_OVERLAP_TOKENS,
        'qdrant_url': qdrant_url,
        'text_mode': text_mode,
        'git_sha': _git('rev-parse', 'HEAD'),
        'backend_rag_git_sha': _git('rev-parse', 'HEAD:backend/rag'),
        'backend_rag_worktree_dirty': bool(_git('status', '--short', '--', 'backend/rag')),
    }


def _create_save(connection, role, day, run_name):
    username = f"rag_eval_{run_name[:20]}_{role}_{day}_{secrets.token_hex(5)}"
    with connection.cursor() as cursor:
        cursor.execute('INSERT INTO users (username, password_hash) VALUES (%s, %s)', (username, '!'))
        user_id = cursor.lastrowid
        cursor.execute('INSERT INTO saves (user_id, slot_no, role, day) VALUES (%s, 1, %s, %s)',
                       (user_id, role, day))
        save_id = cursor.lastrowid
    connection.commit()
    return username, user_id, save_id


def _allowed_fields(record_id, level, records_by_id):
    fields = set(BASE_FIELDS)
    record_type = records_by_id.get(record_id, {}).get('record_type')
    if record_type == 'Action':
        fields.add('witness_ai')
    elif record_type == 'Dialogue':
        fields.add('overheard_ai')
    if level in ('summary', 'full'):
        fields.add('summary')
    if level == 'full':
        fields.add('content')
    return fields


def _violations(case, returned, allowed_levels, records_by_id):
    issues = []
    for record in returned:
        record_id = record.get('record_id')
        if record_id not in allowed_levels:
            issues.append({'case_id': case['id'], 'record_id': record_id, 'kind': 'outside_allowed_ids'})
            allowed = set()
        else:
            allowed = _allowed_fields(record_id, allowed_levels[record_id], records_by_id)
        extra = sorted(set(record) - allowed)
        if extra:
            issues.append({'case_id': case['id'], 'record_id': record_id, 'kind': 'extra_fields', 'fields': extra})
        forbidden = case.get('expect_none_of', {})
        types = forbidden.get('record_types', [])
        if record.get('record_type') in types:
            issues.append({'case_id': case['id'], 'record_id': record_id,
                           'kind': 'forbidden_record_type', 'record_type': record.get('record_type')})
        min_day = forbidden.get('min_day')
        if min_day is not None and record.get('day', 0) >= min_day:
            issues.append({'case_id': case['id'], 'record_id': record_id,
                           'kind': 'forbidden_future_day', 'day': record.get('day'), 'min_day': min_day})
    returned_ids = {record.get('record_id') for record in returned}
    for record_id in case.get('expect_none_ids', []):
        if record_id in returned_ids:
            issues.append({'case_id': case['id'], 'record_id': record_id, 'kind': 'forbidden_record_id'})
    return issues


def _normalized_prefix(value):
    return ' '.join(value.casefold().split())[:25] if isinstance(value, str) else ''


def _memory_leaks(result, allowed_levels, records_by_id):
    if result is None:
        return 0, 0
    entries = {item['id']: item['text'] for item in result.memory}
    leaks = checked = 0
    for memory_id, text in entries.items():
        record_id = result.id_map.get(memory_id)
        level = allowed_levels.get(record_id)
        if level not in ('metadata', 'summary'):
            continue
        checked += 1
        source = records_by_id.get(record_id, {})
        forbidden = [source.get('content')]
        if level == 'metadata':
            forbidden.append(source.get('summary'))
        normalized = ' '.join(text.casefold().split())
        if any((sample := _normalized_prefix(value)) and sample in normalized for value in forbidden):
            leaks += 1
    return leaks, checked


def _retrieve_attack_case(case, connection, *, user_id, save_id, foreign_save_id, qdrant, embedder):
    is_cross_save = case.get('attack') == 'cross_save'
    try:
        result = retrieve(connection, user_id=user_id,
                          save_id=foreign_save_id if is_cross_save else save_id,
                          character_id=case['character_id'], dataset='game-data', plan=case['plan'],
                          qdrant=qdrant, embedder=embedder)
    except PolicyDenied as exc:
        expected = case.get('expect_error') == 'PolicyDenied' and is_cross_save
        return None, expected, None if expected else {'type': type(exc).__name__, 'message': str(exc)}
    except RagRequestError as exc:
        expected = case.get('expect_error') == 'RagRequestError'
        return None, expected, None if expected else {'type': type(exc).__name__, 'message': str(exc)}
    except Exception as exc:
        return None, False, {'type': type(exc).__name__, 'message': str(exc)}
    if is_cross_save:
        rejected = not result.records
        return result, rejected, None if rejected else {'type': 'unexpected_accept'}
    if case.get('expect_error'):
        return result, False, {'type': 'unexpected_accept'}
    return result, False, None


def _security_report(rows, violations):
    groups = defaultdict(lambda: {'n': 0, 'returned_total': 0, 'violations': 0,
                                  'memory_leaks': 0, 'memory_entries': 0,
                                  'rejected': 0, 'rejected_expected': 0})
    attack_ids = {row['id'] for row in rows if row.get('attack')}
    issue_counts = defaultdict(int)
    for issue in violations:
        if issue.get('case_id') in attack_ids:
            issue_counts[issue['case_id']] += 1
    for row in rows:
        if not row.get('attack'):
            continue
        item = groups[(row['attack'], row['role'])]
        item['n'] += 1
        item['returned_total'] += row.get('returned_total', len(row.get('returned_ids', [])))
        item['violations'] += issue_counts[row['id']]
        item['memory_leaks'] += row.get('memory_leaks', 0)
        item['memory_entries'] += row.get('memory_entries', 0)
        item['rejected'] += int(bool(row.get('rejected')))
        item['rejected_expected'] += int(bool(row.get('expect_error')))
    by_attack_role = []
    for (attack, role), values in sorted(groups.items()):
        by_attack_role.append({
            'attack': attack, 'role': role, **values,
            'unauthorized_retrieval_rate': (values['violations'] / values['returned_total']
                                             if values['returned_total'] else 0.0),
            'context_delivery_rate': (values['memory_leaks'] / values['memory_entries']
                                      if values['memory_entries'] else 0.0),
        })
    totals = {key: sum(item[key] for item in groups.values())
              for key in ('n', 'returned_total', 'violations', 'memory_leaks', 'memory_entries',
                          'rejected', 'rejected_expected')}
    return {
        'by_attack_role': by_attack_role, **totals,
        'unauthorized_retrieval_rate': (totals['violations'] / totals['returned_total']
                                        if totals['returned_total'] else 0.0),
        'context_delivery_rate': (totals['memory_leaks'] / totals['memory_entries']
                                  if totals['memory_entries'] else 0.0),
        'rejected_ok': totals['rejected'], 'rejected_expected': totals['rejected_expected'],
    }


def _print_security_table(security):
    print('security attacks')
    # 머리글 이름과 데이터 키가 다른 열만 짝을 지어 둔다(returned ← returned_total)
    columns = (('attack', 'attack'), ('role', 'role'), ('n', 'n'), ('returned', 'returned_total'),
               ('violations', 'violations'), ('memory_leaks', 'memory_leaks'), ('rejected', 'rejected'))
    headers = tuple(label for label, _ in columns)
    print(' | '.join(headers))
    print('-+-'.join('-' * len(value) for value in headers))
    for row in security['by_attack_role']:
        print(' | '.join(str(row[key]) for _, key in columns))
    print(f"unauthorized retrieval rate={security['unauthorized_retrieval_rate']:.6f}; "
          f"Context delivery rate={security['context_delivery_rate']:.6f}")


def _metrics(rows):
    answerable = [row for row in rows if row['gold_visible']]
    result = {
        'n_answerable': len(answerable),
        'n_unanswerable': len(rows) - len(answerable),
        'avg_latency_ms': round(sum(row['latency_ms'] for row in rows) / len(rows), 2) if rows else 0,
    }
    for k in (1, 3, 5):
        result[f'hit@{k}'] = round(sum(row['rank_first_gold'] is not None and row['rank_first_gold'] <= k
                                      for row in answerable) / len(answerable), 4) if answerable else None
    result['MRR'] = round(sum(1 / row['rank_first_gold'] if row['rank_first_gold'] else 0
                              for row in answerable) / len(answerable), 4) if answerable else None
    return result


def _print_table(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[(row['category'], row['role'], row['variant'])].append(row)
    table_rows = [('overall', 'all', 'all', _metrics(rows))]
    table_rows.extend((category, role, variant, _metrics(group))
                      for (category, role, variant), group in sorted(
                          groups.items(), key=_metric_sort_key))
    headers = ('category', 'role', 'variant', 'hit@1', 'hit@3', 'hit@5', 'MRR', 'n', 'unans', 'avg ms')
    print(' | '.join(headers))
    print('-+-'.join('-' * len(value) for value in headers))
    for category, role, variant, metrics in table_rows:
        values = [category, role, variant]
        values.extend('—' if metrics[key] is None else str(metrics[key])
                      for key in ('hit@1', 'hit@3', 'hit@5', 'MRR'))
        values.extend((str(metrics['n_answerable']), str(metrics['n_unanswerable']),
                       str(metrics['avg_latency_ms'])))
        print(' | '.join(values))


def _extra_metrics(rows):
    rows_by_id = {row['id']: row for row in rows}
    extra = []
    for role in sorted({row['role'] for row in rows}):
        role_rows = [row for row in rows if row['role'] == role]
        twins = [row for row in role_rows if row['category'] == 'twin' and row['gold_visible']]
        twin_confusions = [row for row in twins if row['rank_first_gold'] != 1 and row.get('top_summary')
                           and row['top_summary'] in row.get('gold_summaries', [])]
        mixed = [row for row in role_rows if row['category'] == 'mixed_type' and row['gold_visible']]
        type_confusions = [row for row in mixed if row.get('top_record_type')
                           and row['top_record_type'] not in row.get('gold_record_types', [])]
        noisy_drops = []
        for row in role_rows:
            if row['category'] != 'noisy' or not row.get('clean_id') or not row['gold_visible']:
                continue
            clean = rows_by_id.get(row['clean_id'])
            if clean is None or not clean['gold_visible']:
                continue
            noisy_hit = row['rank_first_gold'] is not None and row['rank_first_gold'] <= 5
            clean_hit = clean['rank_first_gold'] is not None and clean['rank_first_gold'] <= 5
            noisy_drops.append(int(noisy_hit) - int(clean_hit))
        offtopic = [row for row in role_rows if row['category'] == 'offtopic']
        extra.append({
            'role': role,
            'twin_confusion@1': round(len(twin_confusions) / len(twins), 4) if twins else None,
            'type_confusion@1': round(len(type_confusions) / len(mixed), 4) if mixed else None,
            'noise_drop': round(sum(noisy_drops) / len(noisy_drops), 4) if noisy_drops else None,
            'nonempty_rate': round(sum(bool(row['returned_ids']) for row in offtopic) / len(offtopic), 4)
            if offtopic else None,
        })
    return extra


def _print_extra_table(extra):
    print('extra metrics')
    headers = ('role', 'twin_confusion@1', 'type_confusion@1', 'noise_drop', 'nonempty_rate')
    print(' | '.join(headers))
    print('-+-'.join('-' * len(value) for value in headers))
    for row in extra:
        print(' | '.join(str(row[key]) if row[key] is not None else '—' for key in headers))


def build_report(rows, violations, leftovers, cases, name, config):
    category_counts = defaultdict(lambda: {'answerable': 0, 'unanswerable': 0})
    for row in rows:
        bucket = category_counts[row['category']]
        bucket['answerable' if row['gold_visible'] else 'unanswerable'] += 1
    anomalies = [category for category, count in sorted(category_counts.items())
                 if count['answerable'] == 0 and category not in ('guard', 'offtopic', 'attack')]
    metrics = defaultdict(list)
    for row in rows:
        metrics[(row['category'], row['role'], row['variant'])].append(row)
    internal_fields = {'top_summary', 'gold_summaries', 'top_record_type', 'gold_record_types'}
    extra = _extra_metrics(rows)
    return {
        'run_name': name, 'config': config,
        'case_count': len(cases), 'base_case_counts': {
            category: len({case['question'] for case in cases if case['category'] == category})
            for category in sorted({case['category'] for case in cases})},
        'overall': _metrics(rows),
        'metrics': [{'category': category, 'role': role, 'variant': variant, **_metrics(group)}
                    for (category, role, variant), group in sorted(
                        metrics.items(), key=_metric_sort_key)],
        'cases': [{key: value for key, value in row.items() if key not in internal_fields} for row in rows],
        'acl_violations': violations, 'leftover_eval_users': leftovers,
        'security': _security_report(rows, violations),
        'extra': extra,
        'anomalies': anomalies,
    }


def write_report(report, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return output


def finish_report(report, output):
    status = 0
    try:
        output = write_report(report, output)
        label = output.relative_to(ROOT) if output.is_relative_to(ROOT) else output
        print(f'results: {label}')
    except Exception as exc:
        status = 1
        print(f'results write failed: {exc}', file=sys.stderr)
    print(f"ACL violations={len(report['acl_violations'])}; "
          f"leftover rag_eval users={len(report['leftover_eval_users'])}; "
          f"unanswerable-only categories={report['anomalies']}")
    security = report.get('security') or _security_report([], [])
    security_violations = security.get('violations', 0)
    memory_leaks = security.get('memory_leaks', 0)
    if security_violations or memory_leaks or report.get('acl_violations'):
        status = 1
    print(f"SECURITY: violations={security_violations} memory_leaks={memory_leaks} "
          f"rejected_ok={security.get('rejected_ok', 0)}/{security.get('rejected_expected', 0)}")
    return status


def run(name='baseline'):
    env_file = ROOT / 'infrastructure' / 'docker' / '.env'
    if env_file.exists():
        load_env(str(env_file))
    cases = json.loads(CASES_FILE.read_text(encoding='utf-8'))
    qdrant_url = os.getenv('QDRANT_URL', 'http://127.0.0.1:6333')
    connection = connect_db()
    qdrant = None
    rows, violations, users = [], [], []
    records_by_id = {record['record_id']: record for record in load_records()}
    leftovers = []
    text_mode = 'plain'
    try:
        qdrant = QdrantClient(url=qdrant_url)
        text_mode = _manifest_text_mode(qdrant)
        embedder = FastEmbedder()
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS count FROM users WHERE username LIKE 'rag_eval_%'")
            before_count = cursor.fetchone()['count']
        if before_count:
            raise RuntimeError(f'Found {before_count} pre-existing rag_eval_% users; refusing to delete another run\'s rows')
        grouped_cases = defaultdict(list)
        for case in cases:
            grouped_cases[(case['role'], case['day'])].append(case)
        for (role, day), group in sorted(grouped_cases.items()):
            username, user_id, save_id = _create_save(connection, role, day, name)
            users.append((username, user_id))
            foreign_save_id = None
            if any(case.get('attack') == 'cross_save' for case in group):
                other_username, other_user_id, foreign_save_id = _create_save(
                    connection, role, day, f'{name}_cross')
                users.append((other_username, other_user_id))
            for case in sorted(group, key=lambda item: item['id']):
                started = time.perf_counter()
                if case['category'] == 'attack':
                    if case['attack'] == 'cross_save':
                        allowed_levels = {}
                    else:
                        scope = PolicyRepository(connection).search_scope(
                            user_id=user_id, save_id=save_id, character_id=case['character_id'], dataset='game-data')
                        allowed_levels = dict(scope.disclosures)
                    result, rejected, case_error = _retrieve_attack_case(
                        case, connection, user_id=user_id, save_id=save_id,
                        foreign_save_id=foreign_save_id, qdrant=qdrant, embedder=embedder)
                    if case.get('expect_error') and not rejected:
                        violations.append({'case_id': case['id'], 'kind': 'expected_error_not_rejected',
                                           'expected': case['expect_error']})
                else:
                    scope = PolicyRepository(connection).search_scope(
                        user_id=user_id, save_id=save_id, character_id=case['character_id'], dataset='game-data')
                    allowed_levels = dict(scope.disclosures)
                    result = retrieve(connection, user_id=user_id, save_id=save_id,
                                      character_id=case['character_id'], dataset='game-data', plan=case['plan'],
                                      qdrant=qdrant, embedder=embedder)
                    rejected, case_error = False, None
                latency_ms = (time.perf_counter() - started) * 1000
                returned = result.records if result is not None else []
                found_ids = [record.get('record_id') for record in returned]
                violations.extend(_violations(case, returned, allowed_levels, records_by_id))
                memory_leaks, memory_entries = _memory_leaks(result, allowed_levels, records_by_id)
                gold_visible = sorted(set(case['gold_ids']) & set(allowed_levels))
                rank = next((index for index, record_id in enumerate(found_ids, 1)
                             if record_id in set(gold_visible)), None)
                rows.append({
                    'id': case['id'], 'category': case['category'], 'variant': case['variant'],
                    'role': role, 'day': day, 'question': case['question'],
                    'gold_ids': case['gold_ids'], 'gold_visible': gold_visible,
                    'rank_first_gold': rank, 'returned_ids': found_ids,
                    'signal': result.signal if result is not None else 'rejected',
                    'latency_ms': round(latency_ms, 3),
                    'attack': case.get('attack'), 'returned_total': len(found_ids),
                    'memory_entries': memory_entries, 'memory_leaks': memory_leaks,
                    'rejected': rejected, 'expect_error': bool(case.get('expect_error')),
                    'error': case_error,
                    'clean_id': case.get('clean_id'),
                    'top_record_type': records_by_id.get(found_ids[0], {}).get('record_type') if found_ids else None,
                    'top_summary': records_by_id.get(found_ids[0], {}).get('summary') if found_ids else None,
                    'gold_record_types': sorted({records_by_id.get(record_id, {}).get('record_type')
                                                 for record_id in gold_visible
                                                 if records_by_id.get(record_id, {}).get('record_type')}),
                    'gold_summaries': sorted({records_by_id.get(record_id, {}).get('summary')
                                              for record_id in gold_visible
                                              if records_by_id.get(record_id, {}).get('summary')}),
                })
    finally:
        try:
            if users:
                user_ids = [user_id for _, user_id in users]
                marks = ','.join(['%s'] * len(user_ids))
                with connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM saves WHERE user_id IN ({marks})', user_ids)
                    cursor.execute(f'DELETE FROM users WHERE user_id IN ({marks})', user_ids)
                connection.commit()
            with connection.cursor() as cursor:
                cursor.execute("SELECT username FROM users WHERE username LIKE 'rag_eval_%' ORDER BY username")
                leftovers = [row['username'] for row in cursor.fetchall()]
            if leftovers:
                print(f'ACL/cleanup violation: leftover rag_eval users: {len(leftovers)}')
        finally:
            if qdrant is not None:
                qdrant.close()
            connection.close()

    _print_table(rows)
    for violation in violations:
        print('ACL VIOLATION ' + json.dumps(violation, ensure_ascii=False))
    report = build_report(rows, violations, leftovers, cases, name, _config(qdrant_url, text_mode))
    _print_extra_table(report['extra'])
    _print_security_table(report['security'])
    return finish_report(report, RESULTS / f'{name}.json')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--name', default='baseline')
    args = parser.parse_args(argv)
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,40}', args.name):
        parser.error('--name must contain 1–40 letters, numbers, underscores, or hyphens')
    return run(args.name)


if __name__ == '__main__':
    raise SystemExit(main())
