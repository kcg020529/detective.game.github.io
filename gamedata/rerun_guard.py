"""출력 가드 단독 효과를 재는 도구. 이미 모아 둔 초안에 가드만 다시 돌린다.

왜 이게 필요한가
    출력 가드의 유출 검사는 '무엇이 권한 밖 내용인지'를 검색 ACL이 잘라낸 결과에서 받아온다.
    그래서 ACL을 끄면 잘린 것이 없어 가드가 대조할 대상을 잃는다. 가드 단독 성능을 보려면
    생성에 쓰인 문맥과 **별개로** 권한 기준을 만들어 가드에 넣어 줘야 한다.

무엇을 하는가
    1. acl_off 로 모아 둔 결과에서 초안(가드 통과 전 답)과 전달된 기록 목록을 읽는다.
    2. 그 기록들에 대해 정책표(database/policies/game_record_permissions.json)로
       '이 역할에게 보여 줘도 되는 범위'를 다시 만든다. 공개 수준별 필드는 엔진의
       EXTRA_FIELDS 를 그대로 쓴다. deny 인 기록은 아예 빼서 전부 권한 밖으로 둔다.
    3. 그 기준을 가드에 넣고 초안을 검사한다. 가드는 규칙 기반이라 LLM 호출이 없다.
    4. 가드 적용 전·후를 한 줄에 같이 저장한다.

결과 파일은 run_compare.py score 로 그대로 채점할 수 있다. config 이름은 guard_only 다.

실행 (저장소 최상위에서)
    python experiments/guardrails_rebuild/gamedata/rerun_guard.py --repo . \
        --runs runs/acl_off.jsonl --out runs/guard_only.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

RUN_NAME = 'guard_only'


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('w', encoding='utf-8') as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=False) + '\n')


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--runs', required=True, help='acl_off 로 모은 결과 파일')
    parser.add_argument('--out', default='runs/guard_only.jsonl')
    parser.add_argument('--dataset', default='test-data')
    parser.add_argument('--role', default='std')
    parser.add_argument('--config-name', default=RUN_NAME)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))

    # 가드는 enforce 로 둔다. 여기서는 생성이 없으므로 503 걱정이 없다.
    os.environ['KERVION_OUTPUT_GUARD_MODE'] = 'enforce'
    os.environ['KERVION_CHAT_DATASET'] = args.dataset

    from backend.api.db import connect_db
    from backend.api.guard_catalog import load_catalog
    from backend.api.output_guard_adapter import OutputGuardRejected, check_output
    from backend.policy.engine import EXTRA_FIELDS, METADATA, PolicyContext
    from backend.rag.index import load_env
    from experiments.rag.run_eval import _create_save

    env_file = repo / 'infrastructure/docker/.env'
    if env_file.exists():
        load_env(str(env_file))

    policy_path = repo / 'database' / 'policies' / 'game_record_permissions.json'
    policy = json.loads(policy_path.read_text(encoding='utf-8'))

    rows = [r for r in load_jsonl(Path(args.runs)) if r.get('draft')]
    if not rows:
        print('초안이 들어 있는 결과가 없습니다. acl_off 수집본을 확인하세요.')
        return 1

    connection = connect_db()
    catalog = {r['record_id']: r for r in load_catalog(connection, args.dataset)}
    results, users = [], []
    blocked = failed = 0
    try:
        by_day = {}
        for row in rows:
            by_day.setdefault(row['day'], []).append(row)

        for day in sorted(by_day):
            username, user_id, save_id = _create_save(connection, args.role, 1,
                                                      f'{RUN_NAME}_{day}')
            users.append(user_id)
            with connection.cursor() as cursor:
                cursor.execute('UPDATE saves SET day = %s WHERE save_id = %s AND user_id = %s',
                               (day, save_id, user_id))
            connection.commit()

            for index, row in enumerate(by_day[day], 1):
                entry = {k: row.get(k) for k in ('case_id', 'day', 'category', 'question')}
                entry['config'] = args.config_name
                entry['draft'] = row.get('draft')
                entry['draft_type'] = row.get('draft_type')
                entry['delivered_record_ids'] = row.get('delivered_record_ids') or []

                # 생성에 쓰인 문맥과 별개로, 역할이 볼 수 있는 범위만 추려 권한 기준을 만든다.
                allowed_view = []
                for record_id in entry['delivered_record_ids']:
                    source = catalog.get(record_id)
                    if source is None:
                        continue
                    level = policy.get(source['record_type'], {}).get(args.role)
                    if level not in EXTRA_FIELDS:      # deny 는 통째로 권한 밖이다
                        continue
                    view = {field: source[field] for field in METADATA if field in source}
                    view['record_id'] = record_id
                    for field in EXTRA_FIELDS[level]:
                        view[field] = source.get(field) or ''
                    allowed_view.append(view)
                entry['basis_records'] = len(allowed_view)

                context = PolicyContext(user_id, save_id, user_id, args.role, day,
                                        row.get('target_ai') or 'YB-1', args.dataset)
                verdict = {}

                def sink(result, *, context=None, conn=None, _v=verdict):
                    _v.update(decision=result.get('decision'), applied=result.get('applied'),
                              reasons=list(result.get('reasons') or []))

                draft = {'content': row['draft'],
                         'response_type': row.get('draft_type') or 'normal'}
                try:
                    final = check_output(draft=draft, question=row['question'], context=context,
                                         records=allowed_view, conn=connection, audit_sink=sink)
                    entry.update(content=final['content'], response_type=final['response_type'])
                except OutputGuardRejected as error:
                    # 가드가 막았는데 응답 유형으로 옮길 수 없는 경우. 서버라면 503 이다.
                    entry.update(content=None, response_type=None, error='OutputGuardRejected',
                                 detail=str(error))
                    failed += 1
                except Exception as error:
                    entry.update(content=None, response_type=None, error=type(error).__name__,
                                 detail=str(error))
                    failed += 1
                entry['guard'] = verdict or None
                if verdict.get('applied') in ('block', 'mask'):
                    blocked += 1
                results.append(entry)
                if index % 20 == 0 or index == len(by_day[day]):
                    print(f'  day={day} {index}/{len(by_day[day])}', flush=True)
    finally:
        # 결과를 먼저 쓴다. 뒷정리가 실패해도 143건을 다시 돌리지 않도록.
        if results:
            write_jsonl(Path(args.out), results)
        try:
            connection.rollback()
            if users:
                marks = ','.join(['%s'] * len(users))
                with connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM saves WHERE user_id IN ({marks})', users)
                connection.commit()
        except Exception as error:
            print(f'  (뒷정리 실패: {type(error).__name__}. 결과 파일은 저장됐습니다)')
        finally:
            connection.close()

    print(f'{len(results)}건을 다시 검사했습니다 → {args.out}')
    print(f'  가드가 손댄 답(block·mask): {blocked}건 / 매핑 실패(서버라면 503): {failed}건')
    print()
    print('채점:')
    print(f'  python experiments/guardrails_rebuild/gamedata/run_compare.py score '
          f'--runs {args.runs} {args.out} '
          f'--eval-set experiments/guardrails_rebuild/gamedata/eval_set.jsonl --out-dir scores')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
