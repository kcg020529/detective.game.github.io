import shutil
import subprocess
from pathlib import Path

import pytest

from backend.api.saves import AdvanceDay, advance_day


ROOT = Path(__file__).resolve().parents[1]


def test_advance_day_replay_uses_current_read():
    class Cursor:
        query = ''
        def __enter__(self): return self
        def __exit__(self, *_): pass
        def execute(self, query, params):
            self.query = query
            if 'FROM request_log' in query:
                assert query.endswith('FOR UPDATE')
        def fetchone(self):
            if 'FROM request_log' in self.query:
                return {'endpoint': 'advance-day', 'response_json': '{"game_state":{"day":2}}'}
            return {'save_id': 1, 'day': 2}

    class Connection:
        def cursor(self): return Cursor()

    response = advance_day(AdvanceDay(client_request_id='same-request'), save_id=1, conn=Connection(), user_id=1)
    assert response == {'game_state': {'day': 2}}


def test_frontend_r23_regressions():
    node = shutil.which('node')
    if not node:
        pytest.skip('Node is not installed')
    result = subprocess.run([node, '--test', str(ROOT / 'tests/frontend/r23.test.cjs')],
                            cwd=ROOT, text=True, encoding='utf-8', capture_output=True)
    assert result.returncode == 0, result.stdout + result.stderr
