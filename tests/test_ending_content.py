import json
import re
from pathlib import Path
from unittest.mock import MagicMock

from backend.api.verdict import VERDICT
from database.loaders.load_mariadb import load_sources
from infrastructure.docker import migrate

ROOT = Path(__file__).resolve().parents[1]


def test_verdict_is_verbatim_and_all_full_record_ids_exist():
    scenario = (ROOT / 'docs/scenario/최종_시나리오.md').read_text(encoding='utf-8')
    assert VERDICT['culprit_id'] == 'YB-4'
    assert '> ' + VERDICT['truth'] in scenario
    rows = {line.split('|')[1].strip(): [cell.strip() for cell in line.split('|')]
            for line in scenario.splitlines() if re.match(r'\| S0[1-4] \|', line)}
    ids = {item['record_id'] for path in (ROOT / 'data/game-data/experiments').rglob('*.json')
           for item in json.loads(path.read_text(encoding='utf-8'))}
    assert [clue['id'] for clue in VERDICT['clues']] == ['S01', 'S02', 'S03', 'S04']
    for clue in VERDICT['clues']:
        assert clue['title'] == rows[clue['id']][2]
        assert clue['text'] == rows[clue['id']][4]
        assert set(clue['records']) <= ids
        assert len(set(clue['records'])) == len(clue['records'])
        assert all(re.fullmatch(r'T\d{2}-[a-z]+-\d{3}', record_id) for record_id in clue['records'])
    records, _, _ = load_sources(ROOT / 'data/game-data', 'game-data')
    assert {record['record_id'] for record in records} == ids


def test_frontend_has_no_real_verdict_content_or_answer():
    for path in (ROOT / 'frontend').rglob('*.js'):
        text = path.read_text(encoding='utf-8')
        assert VERDICT['truth'] not in text
        assert not re.search(r"culprit_id\s*:\s*['\"]YB-4['\"]", text)
        for clue in VERDICT['clues']:
            assert clue['text'] not in text and clue['title'] not in text
    api = (ROOT / 'frontend/play/api.js').read_text(encoding='utf-8')
    mock_verdict = api.split('const verdictData = {', 1)[1].split('const mockState', 1)[0]
    assert 'Mock' in mock_verdict and 'YB-4' not in mock_verdict
    assert '14시' not in mock_verdict and '서버실' not in mock_verdict
    assert "id: 'DEMO-01'" in mock_verdict


def test_new_schemas_are_discovered_in_order_without_database(monkeypatch):
    applied = []
    monkeypatch.setattr(migrate, 'existing_tables', lambda cursor: set())
    monkeypatch.setattr(migrate, 'apply_file', lambda conn, path, **kwargs: applied.append(path.name) or 'applied')
    migrate.migrate(MagicMock())
    assert applied.index('012_audit_events.sql') < applied.index('013_accusations.sql') < applied.index('014_chat_message_records.sql')
    for name in ('013_accusations.sql', '014_chat_message_records.sql'):
        sql = (migrate.SCHEMA_DIR / name).read_text(encoding='utf-8')
        assert len(migrate.split_sql(sql)) == 1
        assert 'ON DELETE CASCADE' in sql
