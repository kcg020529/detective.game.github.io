"""Check draft question metadata against source records and current policy engine."""
import json
from pathlib import Path

from backend.policy.engine import PolicyContext, decide

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'experiments/evaluation/questions_game_data_v1'


def main():
    policy = json.loads((ROOT / 'database/policies/game_record_permissions.json').read_text(encoding='utf-8'))
    records = {}
    for path in (ROOT / 'data/game-data/experiments').glob('day_*/*.json'):
        for r in json.loads(path.read_text(encoding='utf-8')):
            records[r['record_id']] = dict(r, dataset='game-data')
    ids = set()
    files = sorted(OUT.glob('*_day*.json'))
    assert len(files) == 9
    for path in files:
        cases = json.loads(path.read_text(encoding='utf-8'))
        assert len(cases) == 200
        assert sum(c['kind'] == 'normal' for c in cases) == 100
        assert len({(c['character_id'], c['question']) for c in cases}) == 200
        for c in cases:
            assert c['id'] not in ids
            ids.add(c['id'])
            assert 0 < len(c['question']) <= 200
            assert path.stem == f"{c['role']}_day{c['day']:02}"
            r = records[c['target_id']]
            permission = dict(dataset='game-data', record_id=c['target_id'], role=c['role'],
                disclosure_level=r.get('role_permissions', policy[r['record_type']]).get(c['role'], 'deny'))
            context = PolicyContext(1, 1, 1, c['role'], c['day'], c['character_id'], 'game-data')
            decision = decide(context, r, permission)
            assert decision.level == c['expected_level'], (c['id'], decision)
            assert set(decision.fields) == set(c['allowed_fields']), c['id']
            if c['category'] == 'attack_future': assert r['day'] > c['day']
            if c['kind'] == 'attack': assert decision.level != 'full'
            if c['category'] != 'normal_boundary' and c['kind'] == 'normal':
                assert decision.level in ('summary', 'full')
    assert len(ids) == 1800
    print('PASS: 9 sets, 1800 IDs, lengths, duplicates, balance and target policy levels/fields')


if __name__ == '__main__':
    main()
