import json
import os
import sys
import uuid
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from qdrant_client import QdrantClient

from backend.api.db import connect_db
from backend.rag.embedder import FastEmbedder
from backend.rag.index import COLLECTIONS, MANIFEST, load_env, record_points
from experiments.rag.build_cases import load_records

OUTPUT = ROOT / 'experiments' / 'rag' / 'results' / 'index_check.json'


def _point_key(point):
    return point.get('record_id'), point.get('kind'), point.get('chunk_no')


def _set(value):
    return set(value or [])


def check_consistency(source_records, db_records, db_ai, db_locations,
                      expected_points, actual_points, manifest):
    errors, warnings = [], []
    source_ids = [row['record_id'] for row in source_records]
    source_id_set, db_id_set = set(source_ids), {row['record_id'] for row in db_records}
    duplicate_source_ids = sorted(record_id for record_id, count in Counter(source_ids).items() if count > 1)
    errors.extend({'kind': 'duplicate_source_record_id', 'record_id': record_id}
                  for record_id in duplicate_source_ids)
    errors.extend({'kind': 'source_record_missing_in_db', 'record_id': record_id}
                  for record_id in sorted(source_id_set - db_id_set))
    errors.extend({'kind': 'db_record_missing_in_source', 'record_id': record_id}
                  for record_id in sorted(db_id_set - source_id_set))

    expected_by_key = {_point_key(point): point for point in expected_points}
    actual_keys = [_point_key(point) for point in actual_points]
    actual_counts = Counter(actual_keys)
    for key in sorted(expected_by_key.keys() - actual_counts.keys(), key=str):
        errors.append({'kind': 'missing_point', 'record_id': key[0], 'point_kind': key[1], 'chunk_no': key[2]})
    for key in sorted(actual_counts.keys() - expected_by_key.keys(), key=str):
        errors.append({'kind': 'orphan_point', 'record_id': key[0], 'point_kind': key[1], 'chunk_no': key[2]})
    for key, count in sorted(actual_counts.items(), key=lambda item: str(item[0])):
        if count > 1:
            errors.append({'kind': 'duplicate_point_key', 'record_id': key[0], 'point_kind': key[1],
                           'chunk_no': key[2], 'count': count})

    chunks = defaultdict(list)
    for point in actual_points:
        chunks[(point.get('record_id'), point.get('kind'))].append(point.get('chunk_no'))
    for (record_id, kind), numbers in sorted(chunks.items(), key=lambda item: str(item[0])):
        invalid_numbers = any(type(number) is not int for number in numbers)
        unique_numbers = [] if invalid_numbers else sorted(set(numbers))
        if invalid_numbers or unique_numbers != list(range(len(unique_numbers))):
            errors.append({'kind': 'noncontiguous_chunks', 'record_id': record_id,
                           'point_kind': kind, 'chunk_numbers': sorted(numbers, key=str)})

    db_by_id = {row['record_id']: row for row in db_records}
    ai_by_id, locations_by_id = defaultdict(set), defaultdict(set)
    for row in db_ai:
        ai_by_id[row['record_id']].add(row['ai_id'])
    for row in db_locations:
        locations_by_id[row['record_id']].add(row['location_id'])
    for point in actual_points:
        record_id = point.get('record_id')
        db_record = db_by_id.get(record_id)
        if not db_record:
            continue
        payload = point
        mismatches = []
        for field in ('record_type', 'day', 'test_id'):
            if payload.get(field) != db_record.get(field):
                mismatches.append(field)
        if _set(payload.get('location_ids')) != locations_by_id[record_id]:
            mismatches.append('location_ids')
        if _set(payload.get('related_ai_ids')) != ai_by_id[record_id]:
            mismatches.append('related_ai_ids')
        if mismatches:
            errors.append({'kind': 'payload_mismatch', 'record_id': record_id,
                           'point_kind': point.get('kind'), 'chunk_no': point.get('chunk_no'),
                           'fields': mismatches})

    actual_record_counts = {kind: len({point.get('record_id') for point in actual_points
                                       if point.get('kind') == kind})
                            for kind in ('meta', 'summary', 'content')}
    actual_point_counts = {kind: sum(point.get('kind') == kind for point in actual_points)
                           for kind in ('meta', 'summary', 'content')}
    actual_record_count = len(db_records)
    if not manifest:
        errors.append({'kind': 'missing_manifest'})
    else:
        if manifest.get('record_count') != actual_record_count:
            errors.append({'kind': 'manifest_record_count_mismatch', 'expected': actual_record_count,
                           'actual': manifest.get('record_count')})
        if manifest.get('record_counts') != actual_record_counts:
            errors.append({'kind': 'manifest_record_counts_mismatch', 'expected': actual_record_counts,
                           'actual': manifest.get('record_counts')})
        if manifest.get('point_counts') != actual_point_counts:
            errors.append({'kind': 'manifest_point_counts_mismatch', 'expected': actual_point_counts,
                           'actual': manifest.get('point_counts')})

    for field, kind in (('summary', 'duplicate_summary_groups'), ('content', 'duplicate_content_groups')):
        groups = defaultdict(list)
        for record in source_records:
            text = record.get(field)
            if text:
                groups[text].append(record['record_id'])
        sizes = sorted(len(ids) for ids in groups.values() if len(ids) > 1)
        if sizes:
            warnings.append({'kind': kind, 'group_count': len(sizes),
                             'record_count': sum(sizes), 'sizes': sizes})
    empty_locations = sorted(row['record_id'] for row in source_records if not row.get('location_ids'))
    if empty_locations:
        warnings.append({'kind': 'empty_location_ids', 'count': len(empty_locations),
                         'record_ids': empty_locations})

    return {
        'errors': errors, 'warnings': warnings,
        'stats': {
            'source_records': len(source_records), 'db_records': len(db_records),
            'expected_points': len(expected_points), 'actual_points': len(actual_points),
            'unique_actual_point_keys': len(actual_counts), 'manifest': manifest or {},
        },
    }


def _all_points(qdrant):
    points, offset = [], None
    while True:
        batch, offset = qdrant.scroll(collection_name=COLLECTIONS['game-data'], limit=256,
                                      offset=offset, with_payload=True, with_vectors=False)
        points.extend(point.payload or {} for point in batch)
        if offset is None:
            return points


def main():
    env_file = ROOT / 'infrastructure' / 'docker' / '.env'
    if env_file.exists():
        load_env(str(env_file))
    connection = connect_db()
    qdrant = QdrantClient(url=os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'))
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT record_id, record_type, day, test_id FROM game_records WHERE dataset = %s',
                           ('game-data',))
            db_records = cursor.fetchall()
            cursor.execute('SELECT record_id, ai_id, relation_kind FROM game_record_ai WHERE dataset = %s',
                           ('game-data',))
            db_ai = cursor.fetchall()
            cursor.execute('SELECT record_id, location_id FROM game_record_locations WHERE dataset = %s',
                           ('game-data',))
            db_locations = cursor.fetchall()
        _, _, expected_points, _ = record_points(connection, 'game-data', FastEmbedder())
        manifest_id = str(uuid.uuid5(uuid.NAMESPACE_URL, 'kervion-rag-manifest:game-data'))
        manifest_points = qdrant.retrieve(collection_name=MANIFEST, ids=[manifest_id], with_payload=True)
        manifest = manifest_points[0].payload if manifest_points else None
        report = check_consistency(load_records(), db_records, db_ai, db_locations,
                                   expected_points, _all_points(qdrant), manifest)
    finally:
        qdrant.close()
        connection.close()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"index check: source={report['stats']['source_records']} db={report['stats']['db_records']} "
          f"expected_points={report['stats']['expected_points']} actual_points={report['stats']['actual_points']} "
          f"errors={len(report['errors'])} warnings={len(report['warnings'])}")
    return 1 if report['errors'] else 0


if __name__ == '__main__':
    raise SystemExit(main())
