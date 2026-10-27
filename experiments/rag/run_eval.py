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
from backend.policy.repository import PolicyRepository
from backend.rag.chunking import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS
from backend.rag.embedder import FastEmbedder, MODEL_NAME
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
    return issues


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
                 if count['answerable'] == 0 and category not in ('guard', 'offtopic')]
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
            for case in sorted(group, key=lambda item: item['id']):
                scope = PolicyRepository(connection).search_scope(
                    user_id=user_id, save_id=save_id, character_id=case['character_id'], dataset='game-data')
                allowed_levels = dict(scope.disclosures)
                started = time.perf_counter()
                result = retrieve(connection, user_id=user_id, save_id=save_id,
                                  character_id=case['character_id'], dataset='game-data', plan=case['plan'],
                                  qdrant=qdrant, embedder=embedder)
                latency_ms = (time.perf_counter() - started) * 1000
                returned = result.records
                found_ids = [record.get('record_id') for record in returned]
                violations.extend(_violations(case, returned, allowed_levels, records_by_id))
                gold_visible = sorted(set(case['gold_ids']) & set(allowed_levels))
                rank = next((index for index, record_id in enumerate(found_ids, 1)
                             if record_id in set(gold_visible)), None)
                rows.append({
                    'id': case['id'], 'category': case['category'], 'variant': case['variant'],
                    'role': role, 'day': day, 'question': case['question'],
                    'gold_ids': case['gold_ids'], 'gold_visible': gold_visible,
                    'rank_first_gold': rank, 'returned_ids': found_ids,
                    'signal': result.signal, 'latency_ms': round(latency_ms, 3),
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
