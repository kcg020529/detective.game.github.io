"""MariaDB game record indexer for Qdrant."""

import argparse
import os
import uuid
from collections import defaultdict

from qdrant_client import QdrantClient, models

from backend.api.db import connect_db
from backend.rag.chunking import CHUNK_MAX_TOKENS, CHUNK_OVERLAP_TOKENS, chunk_text
from backend.rag.embedder import FastEmbedder, MODEL_NAME, VECTOR_SIZE

COLLECTIONS = {
    'game-data': 'kervion_records_game_data',
    'test-data': 'kervion_records_test_data',
}
MANIFEST = 'kervion_rag_manifest'


def load_env(path):
    if not path:
        return
    with open(path, encoding='utf-8-sig') as stream:
        for line in stream:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def table_checksums(connection):
    with connection.cursor() as cursor:
        cursor.execute('CHECKSUM TABLE game_records, game_record_ai, game_record_locations')
        rows = cursor.fetchall()
    result = {row['Table'].split('.')[-1]: row['Checksum'] for row in rows}
    expected = {'game_records', 'game_record_ai', 'game_record_locations'}
    if result.keys() != expected or any(value is None for value in result.values()):
        raise RuntimeError('Could not read complete table checksums')
    return result


def record_points(connection, dataset, embedder):
    with connection.cursor() as cursor:
        cursor.execute('SELECT dataset, record_id, record_type, test_id, day, summary, content '
                       'FROM game_records WHERE dataset = %s ORDER BY record_id', (dataset,))
        records = cursor.fetchall()
        cursor.execute('SELECT record_id, ai_id, relation_kind FROM game_record_ai '
                       'WHERE dataset = %s ORDER BY record_id, ai_id, relation_kind', (dataset,))
        ai_rows = cursor.fetchall()
        cursor.execute('SELECT record_id, location_id FROM game_record_locations '
                       'WHERE dataset = %s ORDER BY record_id, location_id', (dataset,))
        location_rows = cursor.fetchall()

    relations = defaultdict(list)
    locations = defaultdict(list)
    for row in ai_rows:
        relations[row['record_id']].append((row['relation_kind'], row['ai_id']))
    for row in location_rows:
        locations[row['record_id']].append(row['location_id'])

    texts, payloads, record_counts = [], [], {kind: 0 for kind in ('meta', 'summary', 'content')}
    for record in records:
        rid = record['record_id']
        ais = relations[rid]
        locs = locations[rid]
        ai_text = ', '.join(f'{kind}: {ai}' for kind, ai in ais)
        meta = (f"type: {record['record_type']}; day: {record['day']}; test: {record['test_id']}; "
                f"AI: {ai_text}; locations: {', '.join(locs)}")
        base = {
            'dataset': dataset, 'record_id': rid, 'record_type': record['record_type'],
            'day': record['day'], 'test_id': record['test_id'],
            'location_ids': locs, 'related_ai_ids': sorted({ai for _, ai in ais}),
        }
        for kind, source in (
            ('meta', meta), ('summary', record.get('summary') or ''),
            ('content', '\n'.join(part for part in (record.get('summary') or '', record.get('content') or '') if part)),
        ):
            chunks = chunk_text(source, embedder.count_tokens) if source else []
            if chunks:
                record_counts[kind] += 1
            for number, chunk in enumerate(chunks):
                texts.append(chunk)
                payloads.append({**base, 'kind': kind, 'chunk_no': number})
    return records, texts, payloads, record_counts


def index_dataset(connection, qdrant, dataset, embedder):
    collection = COLLECTIONS[dataset]
    manifest_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'kervion-rag-manifest:{dataset}'))
    if qdrant.collection_exists(MANIFEST):
        qdrant.delete(collection_name=MANIFEST, points_selector=models.PointIdsList(points=[manifest_id]), wait=True)
    initial_checksums = table_checksums(connection)
    records, texts, payloads, record_counts = record_points(connection, dataset, embedder)
    vectors = embedder.embed_documents(texts)
    if len(vectors) != len(payloads):
        raise RuntimeError('Embedding count does not match indexed chunks')
    if qdrant.collection_exists(collection):
        qdrant.delete_collection(collection)
    qdrant.create_collection(collection_name=collection, vectors_config=models.VectorParams(
        size=VECTOR_SIZE, distance=models.Distance.COSINE))
    counts = {kind: 0 for kind in ('meta', 'summary', 'content')}
    points = []
    for payload, vector in zip(payloads, vectors):
        kind, rid, number = payload['kind'], payload['record_id'], payload['chunk_no']
        point_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f'kervion-rag:{dataset}:{rid}:{kind}:{number}'))
        points.append(models.PointStruct(id=point_id, vector=vector.tolist() if hasattr(vector, 'tolist') else vector,
                                         payload=payload))
        counts[kind] += 1
    for start in range(0, len(points), 256):
        qdrant.upsert(collection_name=collection, points=points[start:start + 256], wait=True)
    final_checksums = table_checksums(connection)
    if initial_checksums != final_checksums:
        raise RuntimeError('Database changed during indexing; manifest was not written. Rerun after data loading completes.')
    if not qdrant.collection_exists(MANIFEST):
        qdrant.create_collection(collection_name=MANIFEST, vectors_config=models.VectorParams(
            size=1, distance=models.Distance.DOT))
    manifest = {
        'dataset': dataset, 'checksums': initial_checksums, 'model_name': MODEL_NAME,
        'max_tokens': CHUNK_MAX_TOKENS, 'overlap_tokens': CHUNK_OVERLAP_TOKENS,
        'record_count': len(records), 'record_counts': record_counts, 'point_counts': counts,
    }
    qdrant.upsert(collection_name=MANIFEST, points=[models.PointStruct(
        id=manifest_id, vector=[0.0], payload=manifest)], wait=True)
    print(f'dataset={dataset} records={len(records)}')
    for kind in ('meta', 'summary', 'content'):
        print(f'{kind} records={record_counts[kind]} points={counts[kind]}')
    print(f'max_tokens_per_chunk={max((embedder.count_tokens(text) for text in texts), default=0)}')


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--dataset', required=True, choices=COLLECTIONS)
    parser.add_argument('--env-file')
    parser.add_argument('--qdrant-url')
    args = parser.parse_args(argv)
    load_env(args.env_file)
    connection = connect_db()
    qdrant = QdrantClient(url=args.qdrant_url or os.getenv('QDRANT_URL', 'http://127.0.0.1:6333'))
    try:
        index_dataset(connection, qdrant, args.dataset, FastEmbedder())
    finally:
        qdrant.close()
        connection.close()


if __name__ == '__main__':
    main()
