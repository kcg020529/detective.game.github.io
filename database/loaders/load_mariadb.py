"""Validate authored JSON and atomically import it into the MariaDB schema."""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TYPES = {
    'setup.json': 'Setup', 'actions.json': 'Action',
    'dialogues.json': 'Dialogue', 'thoughts.json': 'Thought',
    'results.json': 'Result', 'incidents.json': 'Incident',
}
AIS = {f'YB-{n}' for n in range(1, 7)}
ROLES = {'prof', 'grad', 'std'}
LEVELS = {'full', 'summary', 'metadata', 'basic_metadata', 'deny'}
LOCATIONS = {'중앙홀', '회의실', '기록실', '전력실', '통신실', '창고', '서버실'}


class ValidationError(ValueError):
    pass


def require(condition, message):
    if not condition:
        raise ValidationError(message)


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, 'JSON object has duplicate keys')
        result[key] = value
    return result


def invalid_constant(value):
    raise ValidationError('non-finite numbers are not valid JSON')


def read_json(path):
    try:
        return json.loads(path.read_text(encoding='utf-8-sig'),
                          object_pairs_hook=unique_object, parse_constant=invalid_constant)
    except (ValueError, OSError) as exc:
        raise ValidationError(f'{path}: invalid or unreadable JSON') from exc


def array(record, key, choices, *, missing=False):
    require(key in record or missing, f'missing {key}')
    value = record.get(key, [])
    require(isinstance(value, list), f'{key} must be an array')
    require(all(isinstance(v, str) and v in choices for v in value),
            f'{key} contains an unsupported value')
    require(len(value) == len(set(value)), f'{key} has duplicates')
    return value


def text(record, key):
    require(isinstance(record.get(key), str) and record[key].strip(),
            f'{key} must be nonempty text')


def validate_record(raw, dataset, default_level=None, allow_missing_locations=False):
    require(isinstance(raw, dict), 'each record must be an object')
    record = dict(raw)
    for key in ('record_id', 'record_type', 'summary', 'content'):
        text(record, key)
    require(record['record_type'] in TYPES.values(), 'unsupported record_type')
    require(type(record.get('test_id')) is int and 1 <= record['test_id'] <= 30,
            'test_id must be an integer in 1..30')
    require(type(record.get('day')) is int and 1 <= record['day'] <= 6,
            'day must be an integer in 1..6')
    if dataset == 'game-data':
        require(record['day'] == (record['test_id'] - 1) // 5 + 1,
                'game-data day and test_id disagree')
    prefix = f"T{record['test_id']:02d}-{record['record_type'].lower()}-"
    require(re.fullmatch(re.escape(prefix) + r'[0-9]{3}', record['record_id'])
            and not record['record_id'].endswith('-000'), 'record_id disagrees with fields')
    participants = array(record, 'involved_ai', AIS)
    require(bool(participants), 'involved_ai must not be empty')
    if record['record_type'] == 'Thought':
        require(len(participants) == 1, 'Thought must have one owner')
    record['location_ids'] = array(record, 'location_ids', LOCATIONS,
                                   missing=allow_missing_locations)
    for key, kind in (('witness_ai', 'Action'), ('overheard_ai', 'Dialogue')):
        if record['record_type'] == kind:
            observers = array(record, key, AIS)
            require(not set(participants) & set(observers), f'{key} overlaps involved_ai')
        else:
            require(key not in record, f'{key} is invalid for this record_type')
    array(record, 'allowed_roles', ROLES)
    level = record.get('disclosure_level', default_level)
    require(isinstance(level, str) and level in LEVELS,
            'disclosure_level is required; explicitly set --default-disclosure if intended')
    record['disclosure_level'] = level
    return record


def validate_rules(raw):
    require(isinstance(raw, dict), 'rules must be an object')
    for key in ('rule_id', 'title', 'description'):
        text(raw, key)
    require(re.fullmatch(r'[A-Za-z0-9_-]{1,64}', raw['rule_id']), 'invalid rule_id')
    require(len(raw['title']) <= 255, 'rule title is too long')
    require(bool(array(raw, 'involved_ai', AIS)), 'rules need involved_ai')
    array(raw, 'allowed_roles', ROLES)
    require(raw.get('disclosure_level') in ('full', 'deny'),
            'shared rules currently support full or deny only')
    for key, expected in (('participants', 6), ('seeker_count', 2), ('runner_count', 4),
                          ('experiment_days', 6), ('experiments_per_day', 5),
                          ('total_experiments', 30), ('time_limit_seconds', 300)):
        require(type(raw.get(key)) is int and raw[key] == expected,
                f'rules {key} disagrees with current game contract')
    require(isinstance(raw.get('scoring'), dict), 'rules scoring must be an object')
    return dict(raw)


def load_sources(source, dataset, default_level=None, allow_missing_locations=False):
    require(source.is_dir(), f'source directory not found: {source}')
    if dataset == 'game-data':
        files = sorted((source / 'experiments').glob('day_*/*.json'))
    else:
        files = sorted(source.rglob('*.json'))
    require(bool(files), 'no record JSON files found')
    records, seen, missing_locations = [], set(), 0
    for path in files:
        rows = read_json(path)
        require(isinstance(rows, list), f'{path}: expected a record array')
        if dataset == 'game-data':
            require(path.name in TYPES, f'{path}: unknown experiment file')
            match = re.fullmatch(r'day_0([1-6])', path.parent.name)
            require(match is not None, f'{path}: invalid Day directory')
        for raw in rows:
            try:
                record = validate_record(raw, dataset, default_level, allow_missing_locations)
                if dataset == 'game-data':
                    require(record['record_type'] == TYPES[path.name], 'file/type mismatch')
                    require(record['day'] == int(match.group(1)), 'directory/day mismatch')
                require(record['record_id'] not in seen, 'duplicate record_id in source')
            except ValidationError as exc:
                raise ValidationError(f'{path}: {exc}') from exc
            missing_locations += int('location_ids' not in raw)
            seen.add(record['record_id'])
            records.append(record)
    rules_path = source / 'rules.json'
    rules = validate_rules(read_json(rules_path)) if dataset == 'game-data' and rules_path.exists() else None
    return records, rules, missing_locations


def import_records(connection, dataset, records, rules=None):
    """Caller provides an autocommit=False connection; one atomic batch."""
    try:
        connection.begin()
        with connection.cursor() as cursor:
            cursor.execute('SELECT location_id FROM locations')
            available = {row[0] for row in cursor.fetchall()}
            required = {loc for r in records for loc in r['location_ids']}
            require(required <= available, 'target locations are missing; apply schema 007 first')
            for r in sorted(records, key=lambda item: item['record_id']):
                key = (dataset, r['record_id'])
                # Clear owned child rows before a possible parent record_type update.
                for table in ('game_record_ai', 'game_record_locations', 'document_permissions'):
                    cursor.execute(f'DELETE FROM {table} WHERE dataset=%s AND record_id=%s', key)
                cursor.execute(
                    'INSERT INTO game_records '
                    '(dataset, record_id, record_type, test_id, day, summary, content) '
                    'VALUES (%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE '
                    'record_type=VALUES(record_type), test_id=VALUES(test_id), '
                    'day=VALUES(day), summary=VALUES(summary), content=VALUES(content)',
                    (*key, r['record_type'], r['test_id'], r['day'], r['summary'], r['content']))
                for field, kind in (('involved_ai', 'involved'), ('witness_ai', 'witness'),
                                    ('overheard_ai', 'overheard')):
                    rows = [(*key, r['record_type'], ai, kind) for ai in r.get(field, [])]
                    if rows:
                        cursor.executemany('INSERT INTO game_record_ai '
                                           '(dataset,record_id,record_type,ai_id,relation_kind) '
                                           'VALUES (%s,%s,%s,%s,%s)', rows)
                if r['location_ids']:
                    cursor.executemany('INSERT INTO game_record_locations '
                                       '(dataset,record_id,location_id) VALUES (%s,%s,%s)',
                                       [(*key, loc) for loc in r['location_ids']])
                if r['allowed_roles']:
                    cursor.executemany('INSERT INTO document_permissions '
                                       '(dataset,record_id,role,disclosure_level) VALUES (%s,%s,%s,%s)',
                                       [(*key, role, r['disclosure_level']) for role in r['allowed_roles']])
            if rules is not None:
                body = {k: v for k, v in rules.items() if k not in {
                    'rule_id', 'title', 'description', 'involved_ai', 'allowed_roles', 'disclosure_level'}}
                encode = lambda value: json.dumps(value, ensure_ascii=False, allow_nan=False)
                cursor.execute('INSERT INTO game_rules '
                               '(dataset,rule_id,title,description,content,involved_ai,allowed_roles,disclosure_level) '
                               'VALUES (%s,%s,%s,%s,%s,%s,%s,%s) ON DUPLICATE KEY UPDATE '
                               'title=VALUES(title), description=VALUES(description), content=VALUES(content), '
                               'involved_ai=VALUES(involved_ai), allowed_roles=VALUES(allowed_roles), '
                               'disclosure_level=VALUES(disclosure_level)',
                               (dataset, rules['rule_id'], rules['title'], rules['description'],
                                encode(body), encode(rules['involved_ai']), encode(rules['allowed_roles']),
                                rules['disclosure_level']))
        connection.commit()
    except Exception:
        connection.rollback()
        raise


def connection_settings(env_file=None):
    values = {}
    if env_file:
        for line in Path(env_file).read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            require('=' in line, 'invalid env file line')
            key, value = line.split('=', 1)
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
                value = value[1:-1]
            values[key.strip()] = value
    values.update(os.environ)
    for key in ('MARIADB_DATABASE', 'MARIADB_USER', 'MARIADB_PASSWORD'):
        require(bool(values.get(key)), f'{key} must be set')
    try:
        port = int(values.get('MARIADB_PORT', '3306'))
        require(1 <= port <= 65535, 'invalid MARIADB_PORT')
    except ValueError as exc:
        raise ValidationError('invalid MARIADB_PORT') from exc
    settings = dict(host=values.get('MARIADB_HOST', '127.0.0.1'), port=port,
                    user=values['MARIADB_USER'], password=values['MARIADB_PASSWORD'],
                    database=values['MARIADB_DATABASE'], charset='utf8mb4',
                    autocommit=False, connect_timeout=10, read_timeout=60, write_timeout=60)
    if values.get('MARIADB_SSL_CA'):
        settings.update(ssl_ca=values['MARIADB_SSL_CA'], ssl_verify_cert=True,
                        ssl_verify_identity=True)
    return settings


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dataset', choices=('test-data', 'game-data'), required=True)
    parser.add_argument('--source', type=Path, help='dataset directory; defaults to repository data/<dataset>')
    parser.add_argument('--env-file', type=Path, help='optional simple KEY=VALUE file; environment takes precedence')
    parser.add_argument('--default-disclosure', choices=sorted(LEVELS),
                        help='explicit level for records without disclosure_level; never inferred from roles')
    parser.add_argument('--allow-missing-locations', action='store_true',
                        help='explicit legacy compatibility: missing location_ids becomes []')
    parser.add_argument('--dry-run', action='store_true', help='validate sources without connecting to DB')
    args = parser.parse_args(argv)
    connection = None
    try:
        records, rules, missing = load_sources(args.source or ROOT / 'data' / args.dataset,
                                              args.dataset, args.default_disclosure,
                                              args.allow_missing_locations)
        print(f'Validated {len(records)} records: {dict(Counter(r["record_type"] for r in records))}; '
              f'common rules: {int(rules is not None)}; missing locations accepted: {missing}')
        if args.dry_run:
            return 0
        import pymysql
        connection = pymysql.connect(**connection_settings(args.env_file))
        import_records(connection, args.dataset, records, rules)
        print('Committed successfully. Existing matching records and their relations/permissions were replaced.')
        return 0
    except (ValidationError, OSError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1
    except ImportError:
        print('Install dependencies: python -m pip install -r database/loaders/requirements.txt', file=sys.stderr)
        return 1
    except Exception:
        # DB errors may contain data or credentials; do not dump exception text.
        print('Database import failed; batch rolled back if started. Check connectivity, grants and schemas 001..008.',
              file=sys.stderr)
        return 1
    finally:
        if connection is not None:
            connection.close()


if __name__ == '__main__':
    raise SystemExit(main())
