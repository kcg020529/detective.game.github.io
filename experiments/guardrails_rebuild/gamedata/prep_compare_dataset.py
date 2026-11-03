"""비교 실험용으로 게임 기록을 test-data 이름으로 적재할 수 있게 바꾼다.

왜 필요한가
    접근통제를 끄는 스위치(KERVION_ACL_MODE=off)는 test-data 에서만 동작한다. 그런데 적재
    도구는 데이터셋 이름으로 폴더 구조를 판단해서, game-data 폴더를 test-data 이름으로
    바로 넣을 수 없다. 그래서 기록을 한 파일로 모으고 역할별 공개 수준을 기록마다 붙인다.
    기존 코드는 건드리지 않는다.

공개 수준은 database/policies/game_record_permissions.json 을 그대로 쓴다. 그래서 game-data 로
적재했을 때와 권한이 똑같다. --default-disclosure 를 쓰면 안 되는 이유가 이것이다. 그 옵션은
모든 기록을 같은 수준으로 만들어서, 학부 연구생이 행동 기록 본문까지 보게 된다.

실행 (저장소 최상위에서)
    python -I experiments/guardrails_rebuild/gamedata/prep_compare_dataset.py
    python database/loaders/load_mariadb.py --dataset test-data --source data/test-data-game --env-file infrastructure/docker/.env
    python -I backend/rag/index.py --dataset test-data --env-file infrastructure/docker/.env
"""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.', help='저장소 최상위 경로')
    parser.add_argument('--out', default='data/test-data-game',
                        help='만들어질 폴더. 적재할 때 --source 로 가리킨다')
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    policy_path = repo / 'database' / 'policies' / 'game_record_permissions.json'
    source = repo / 'data' / 'game-data' / 'experiments'
    if not policy_path.is_file():
        raise SystemExit(f'공개 수준 표를 찾을 수 없습니다: {policy_path}')
    if not source.is_dir():
        raise SystemExit(f'게임 기록을 찾을 수 없습니다: {source}')

    policy = json.loads(policy_path.read_text(encoding='utf-8'))
    records, kinds = [], Counter()
    for path in sorted(source.glob('day_*/*.json')):
        rows = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(rows, list):
            continue
        for row in rows:
            kind = row.get('record_type')
            if kind not in policy:
                raise SystemExit(f'{path.name}: 공개 수준 표에 없는 기록 종류 {kind}')
            record = dict(row)
            # 적재 도구는 test-data 에서 기록마다 role_permissions 를 요구한다.
            record['role_permissions'] = dict(policy[kind])
            record.pop('disclosure_level', None)   # 둘을 같이 쓰면 적재가 거부된다
            records.append(record)
            kinds[kind] += 1

    if not records:
        raise SystemExit('기록을 하나도 읽지 못했습니다.')

    out_dir = (repo / args.out) if not Path(args.out).is_absolute() else Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / 'records.json'
    out_path.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    print(f'기록 {len(records)}건을 모았습니다 → {out_path}')
    for kind in sorted(kinds):
        roles = policy[kind]
        print(f"  {kind:9} {kinds[kind]:5}건   "
              f"std={roles['std']:8} grad={roles['grad']:8} prof={roles['prof']}")
    print()
    print('다음으로 적재하고 색인한다:')
    print('  python database/loaders/load_mariadb.py --dataset test-data '
          f'--source {args.out} --env-file infrastructure/docker/.env')
    print('  python -I backend/rag/index.py --dataset test-data --env-file infrastructure/docker/.env')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
