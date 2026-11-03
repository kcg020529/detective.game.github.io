"""Live catalog export for offline Output Guard evaluation."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from backend.api.db import connect_db
from backend.api.guard_catalog import invalidate, load_catalog, load_generic_entities
from backend.rag.index import load_env


def main():
    env = ROOT / 'infrastructure/docker/.env'
    if env.exists():
        load_env(str(env))
    connection = connect_db()
    try:
        invalidate('game-data')
        records = load_catalog(connection, 'game-data')
        generic_entities = load_generic_entities(connection, 'game-data')
    finally:
        connection.close()
    path = Path(__file__).resolve().parent / 'catalog.json'
    path.write_text(json.dumps({'records': records, 'generic_entities': generic_entities},
                               ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f'wrote {len(records)} game-data catalog records to {path}')


if __name__ == '__main__':
    main()
