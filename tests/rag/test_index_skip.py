from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.rag import index


@pytest.fixture
def indexing(monkeypatch):
    conn = Mock()
    monkeypatch.setattr(index, 'table_checksums', Mock(return_value={'game_records': 1}))
    points = Mock(return_value=([{}], [], [], {'meta': 0, 'summary': 0, 'content': 0}))
    monkeypatch.setattr(index, 'record_points', points)
    manifest = {
        'dataset': 'game-data', 'checksums': {'game_records': 1}, 'model_name': index.MODEL_NAME,
        'max_tokens': index.CHUNK_MAX_TOKENS, 'overlap_tokens': index.CHUNK_OVERLAP_TOKENS,
        'text_mode': 'header', 'point_counts': {'meta': 1, 'summary': 1, 'content': 1},
    }
    qdrant = Mock()
    qdrant.collection_exists.return_value = True
    qdrant.retrieve.return_value = [SimpleNamespace(payload=manifest)]
    qdrant.count.side_effect = lambda **kw: SimpleNamespace(count=1 if 'count_filter' in kw else 3)
    embedder = Mock()
    embedder.embed_documents.return_value = []
    return conn, qdrant, embedder, manifest, points


def test_unchanged_index_skips_without_mutations_or_embedding(indexing, capsys):
    conn, qdrant, embedder, _, points = indexing
    index.index_dataset(conn, qdrant, 'game-data', embedder)
    assert 'skipping index' in capsys.readouterr().out
    for method in (qdrant.delete_collection, qdrant.delete, qdrant.create_collection, qdrant.upsert,
                   embedder.embed_documents, points):
        method.assert_not_called()


@pytest.mark.parametrize('change', ['dataset', 'checksums', 'model_name', 'max_tokens', 'overlap_tokens',
                                   'text_mode', 'missing_collection', 'missing_manifest', 'point_counts',
                                   'kind_count', 'total_count', 'force'])
def test_changed_or_incomplete_index_rebuilds(indexing, change):
    conn, qdrant, embedder, manifest, points = indexing
    if change in manifest:
        manifest[change] = {} if change == 'point_counts' else 'changed'
    elif change == 'missing_collection':
        qdrant.collection_exists.side_effect = lambda name: name != index.COLLECTIONS['game-data']
    elif change == 'missing_manifest':
        qdrant.retrieve.return_value = []
    elif change == 'kind_count':
        qdrant.count.side_effect = lambda **kw: SimpleNamespace(count=0 if 'count_filter' in kw else 3)
    elif change == 'total_count':
        qdrant.count.return_value = SimpleNamespace(count=4)
        qdrant.count.side_effect = None
    index.index_dataset(conn, qdrant, 'game-data', embedder, force=change == 'force')
    points.assert_called_once()
    embedder.embed_documents.assert_called_once()
    assert any(call.kwargs.get('collection_name') == index.COLLECTIONS['game-data']
               for call in qdrant.create_collection.call_args_list)
    if change != 'missing_collection':
        qdrant.delete_collection.assert_called_once_with(index.COLLECTIONS['game-data'])


@pytest.mark.parametrize('cli,env,force', [([], '1', True), (['--force'], '', True), ([], '', False)])
def test_index_main_force_flag_and_environment(monkeypatch, cli, env, force):
    monkeypatch.setenv('KERVION_RAG_FORCE', env)
    monkeypatch.setattr(index, 'connect_db', Mock())
    monkeypatch.setattr(index, 'QdrantClient', Mock())
    run = Mock()
    monkeypatch.setattr(index, 'index_dataset', run)
    index.main(['--dataset', 'game-data', *cli])
    assert run.call_args.kwargs['force'] is force
