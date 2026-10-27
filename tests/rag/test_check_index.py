from copy import deepcopy

import pytest

from experiments.rag.check_index import check_consistency


def _fixture():
    source = [
        {'record_id': 'R1', 'record_type': 'Action', 'day': 1, 'test_id': 1,
         'summary': 'move one', 'content': 'body one', 'location_ids': ['room-a'], 'involved_ai': ['YB-1']},
        {'record_id': 'R2', 'record_type': 'Dialogue', 'day': 1, 'test_id': 1,
         'summary': 'talk two', 'content': 'body two', 'location_ids': ['room-b'], 'involved_ai': ['YB-2']},
    ]
    db_records = [{'record_id': 'R1', 'record_type': 'Action', 'day': 1, 'test_id': 1},
                  {'record_id': 'R2', 'record_type': 'Dialogue', 'day': 1, 'test_id': 1}]
    db_ai = [{'record_id': 'R1', 'ai_id': 'YB-1'}, {'record_id': 'R2', 'ai_id': 'YB-2'}]
    db_locations = [{'record_id': 'R1', 'location_id': 'room-a'},
                    {'record_id': 'R2', 'location_id': 'room-b'}]
    points = [
        {'record_id': 'R1', 'kind': 'meta', 'chunk_no': 0, 'record_type': 'Action', 'day': 1,
         'test_id': 1, 'location_ids': ['room-a'], 'related_ai_ids': ['YB-1']},
        {'record_id': 'R1', 'kind': 'summary', 'chunk_no': 0, 'record_type': 'Action', 'day': 1,
         'test_id': 1, 'location_ids': ['room-a'], 'related_ai_ids': ['YB-1']},
        {'record_id': 'R2', 'kind': 'meta', 'chunk_no': 0, 'record_type': 'Dialogue', 'day': 1,
         'test_id': 1, 'location_ids': ['room-b'], 'related_ai_ids': ['YB-2']},
    ]
    manifest = {'record_count': 2, 'record_counts': {'meta': 2, 'summary': 1, 'content': 0},
                'point_counts': {'meta': 2, 'summary': 1, 'content': 0}}
    return source, db_records, db_ai, db_locations, points, manifest


def _check(source=None, db_records=None, db_ai=None, db_locations=None, expected=None, actual=None, manifest=None):
    base = _fixture()
    return check_consistency(source if source is not None else base[0],
                             db_records if db_records is not None else base[1],
                             db_ai if db_ai is not None else base[2],
                             db_locations if db_locations is not None else base[3],
                             expected if expected is not None else base[4],
                             actual if actual is not None else base[4],
                             manifest if manifest is not None else base[5])


def _assert_one_error(report, kind):
    assert [error['kind'] for error in report['errors']] == [kind]


def test_clean_index_has_no_errors():
    report = _check()
    assert report['errors'] == []
    assert report['warnings'] == []


def test_source_record_missing_from_database():
    source, *_ = _fixture()
    source.append({**source[0], 'record_id': 'R3'})
    _assert_one_error(_check(source=source), 'source_record_missing_in_db')


def test_database_record_missing_from_source():
    _, db_records, *_ = _fixture()
    db_records.append({'record_id': 'R3', 'record_type': 'Action', 'day': 1, 'test_id': 1})
    manifest = _fixture()[-1] | {'record_count': 3}
    _assert_one_error(_check(db_records=db_records, manifest=manifest), 'db_record_missing_in_source')


def test_duplicate_json_record_id():
    source, *_ = _fixture()
    source.append(deepcopy(source[0]))
    _assert_one_error(_check(source=source), 'duplicate_source_record_id')


def test_missing_qdrant_point():
    *_, points, manifest = _fixture()
    actual = points[:-1]
    manifest = deepcopy(manifest)
    manifest['point_counts']['meta'] = 1
    manifest['record_counts']['meta'] = 1
    _assert_one_error(_check(actual=actual, manifest=manifest), 'missing_point')


def test_orphan_qdrant_point():
    *_, points, manifest = _fixture()
    actual = [*points, {**points[0], 'record_id': 'R99'}]
    manifest = deepcopy(manifest)
    manifest['record_counts']['meta'] = 3
    manifest['point_counts']['meta'] = 3
    _assert_one_error(_check(actual=actual, manifest=manifest), 'orphan_point')


def test_duplicate_qdrant_key():
    *_, points, manifest = _fixture()
    actual = [*points, deepcopy(points[0])]
    manifest = deepcopy(manifest)
    manifest['point_counts']['meta'] = 3
    _assert_one_error(_check(actual=actual, manifest=manifest), 'duplicate_point_key')


def test_noncontiguous_chunk_numbers():
    *_, points, manifest = _fixture()
    gap = {**points[0], 'chunk_no': 2}
    expected, actual = [*points, gap], [*points, deepcopy(gap)]
    manifest = deepcopy(manifest)
    manifest['point_counts']['meta'] = 3
    _assert_one_error(_check(expected=expected, actual=actual, manifest=manifest), 'noncontiguous_chunks')


@pytest.mark.parametrize(('field', 'value'), [
    ('record_type', 'Setup'), ('day', 2), ('test_id', 2),
    ('location_ids', ['room-b']), ('related_ai_ids', ['YB-2']),
])
def test_database_payload_mismatch(field, value):
    *_, points, _manifest = _fixture()
    actual = deepcopy(points)
    actual[0][field] = value
    report = _check(actual=actual)
    _assert_one_error(report, 'payload_mismatch')
    assert report['errors'][0]['fields'] == [field]


@pytest.mark.parametrize(('field', 'kind'), [
    ('record_count', 'manifest_record_count_mismatch'),
    ('record_counts', 'manifest_record_counts_mismatch'),
    ('point_counts', 'manifest_point_counts_mismatch'),
])
def test_manifest_counts_must_match(field, kind):
    manifest = deepcopy(_fixture()[-1])
    if field == 'record_count':
        manifest[field] = 99
    else:
        manifest[field] = {**manifest[field], 'meta': 99}
    _assert_one_error(_check(manifest=manifest), kind)


def test_duplicate_summary_and_content_and_empty_locations_are_warnings():
    source, *_ = _fixture()
    source[1]['summary'] = source[0]['summary']
    source[1]['content'] = source[0]['content']
    source[1]['location_ids'] = []
    report = _check(source=source)
    assert report['errors'] == []
    assert {warning['kind'] for warning in report['warnings']} == {
        'duplicate_summary_groups', 'duplicate_content_groups', 'empty_location_ids'}
