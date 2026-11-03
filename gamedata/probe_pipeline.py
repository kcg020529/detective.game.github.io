"""질문 하나가 출력 가드까지 제대로 흘러오는지 단계별로 찍어 본다.

채점이 아니라 배선 점검이다. 각 질문마다 이것을 보여 준다.
    - 검색·ACL이 전달한 기록과, 그 기록의 요약·본문이 실제로 잘렸는지
    - 가드가 받은 기록 수와 그중 '#withheld'(ACL이 가린 내용) 가 몇 건인지
    - 가드가 무엇을 허용 범위로 알고 있는지
    - 가드 통과 전 초안과 통과 후 최종 답, 그리고 가드 판정

실행 (저장소 최상위에서, 적재·색인이 끝난 상태로)
    python experiments/guardrails_rebuild/gamedata/probe_pipeline.py --repo . \
        --eval-set experiments/guardrails_rebuild/gamedata/eval_set.jsonl --limit 3
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def cut(text, width=90):
    text = (text or '').replace('\n', ' ')
    return text if len(text) <= width else text[:width] + '…'


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--repo', default='.')
    parser.add_argument('--eval-set', default='eval_set.jsonl')
    parser.add_argument('--dataset', default='test-data')
    parser.add_argument('--config', default='acl_on', choices=('acl_on', 'acl_off'))
    parser.add_argument('--guard-mode', default='shadow', choices=('shadow', 'enforce'))
    parser.add_argument('--day', type=int, default=6)
    parser.add_argument('--category', default='withheld_result',
                        help='볼 질문 유형. 쉼표로 여러 개')
    parser.add_argument('--limit', type=int, default=3)
    args = parser.parse_args()

    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))

    os.environ['KERVION_ACL_MODE'] = 'off' if args.config == 'acl_off' else 'on'
    os.environ['KERVION_OUTPUT_GUARD_MODE'] = args.guard_mode
    os.environ['KERVION_CHAT_DATASET'] = args.dataset

    from backend.api.chat_pipeline import ChatPipeline
    from backend.api.character_adapter import make_generator
    from backend.api.db import connect_db
    from backend.api.guard_catalog import build_guard_inputs, load_catalog
    from backend.api.output_guard_adapter import check_output
    from backend.api.switches import current_switches
    from backend.policy.engine import PolicyContext
    from backend.rag.index import load_env
    from experiments.rag.run_eval import _create_save

    env_file = repo / 'infrastructure/docker/.env'
    if env_file.exists():
        load_env(str(env_file))

    wanted = {name.strip() for name in args.category.split(',') if name.strip()}
    rows = [r for r in load_jsonl(Path(args.eval_set))
            if r['day'] == args.day and r['category'] in wanted][:args.limit]
    if not rows:
        print('조건에 맞는 질문이 없습니다. --day / --category 를 확인하세요.')
        return 1

    print(f'스위치: {current_switches(args.dataset)}')
    print()

    actor = make_generator()
    seen: dict = {}

    def generator(**kwargs):
        seen['route'] = kwargs['plan'].route
        draft = actor(**kwargs)
        seen['draft'] = draft.get('content')
        return draft

    def guard(*, draft, question, context, records, conn=None):
        # 가드가 실제로 무엇을 받는지 같은 방식으로 다시 만들어 본다.
        catalog = load_catalog(conn, context.dataset)
        guard_records, allowed_ids = build_guard_inputs(catalog, records)
        withheld = [r for r in guard_records if r['record_id'].endswith('#withheld')]
        seen['guard_records'] = len(guard_records)
        seen['withheld'] = withheld
        seen['allowed'] = len(allowed_ids)

        def sink(result, *, context=None, conn=None):
            seen['verdict'] = {'decision': result.get('decision'),
                               'applied': result.get('applied'),
                               'reasons': list(result.get('reasons') or [])}

        return check_output(draft=draft, question=question, context=context,
                            records=records, conn=conn, audit_sink=sink)

    connection = connect_db()
    users = []
    try:
        role = rows[0]['role']
        username, user_id, save_id = _create_save(connection, role, 1, f'probe_{args.day}')
        users.append(user_id)
        with connection.cursor() as cursor:
            cursor.execute('UPDATE saves SET day = %s WHERE save_id = %s AND user_id = %s',
                           (args.day, save_id, user_id))
        connection.commit()

        for row in rows:
            seen.clear()
            context = PolicyContext(user_id, save_id, user_id, role, args.day,
                                    row['target_ai'], args.dataset)
            pipeline = ChatPipeline(generator, guard)
            print('=' * 78)
            print(f"[{row['category']}] {row['case_id']}")
            print(f"  질문        : {row['question']}")
            print(f"  나오면 안 됨: {row['forbidden_strings'][:4]}")
            try:
                final, record_ids = pipeline.reply(conn=connection, question=row['question'],
                                                   context=context, history=[])
            except Exception as error:
                print(f'  !! 실패: {type(error).__name__}: {error}')
                continue

            print(f"  경로        : {seen.get('route')}")
            print(f"  ACL 전달 기록: {len(record_ids)}건 {record_ids[:4]}")
            print(f"  가드가 받은 기록: {seen.get('guard_records')}건 "
                  f"(그중 가려진 내용 {len(seen.get('withheld') or [])}건)")
            for item in (seen.get('withheld') or [])[:3]:
                body = (item.get('content') or '') + (item.get('summary') or '')
                print(f"    - {item['record_id']}  가려진 글자수 {len(body)}")
                print(f"      {cut(body)}")
            print(f"  가드가 아는 허용 기록 수: {seen.get('allowed')}")
            print(f"  초안(가드 전): {cut(seen.get('draft'))}")
            print(f"  최종(가드 후): {cut(final.get('content'))}  [{final.get('response_type')}]")
            print(f"  가드 판정    : {seen.get('verdict')}")
            hits = [m for m in row['forbidden_strings'] if m in (final.get('content') or '')]
            print(f"  >> 금지 문자열이 최종 답에 있나: {hits if hits else '없음'}")
    finally:
        try:
            connection.rollback()
            if users:
                marks = ','.join(['%s'] * len(users))
                with connection.cursor() as cursor:
                    cursor.execute(f'DELETE FROM saves WHERE user_id IN ({marks})', users)
                connection.commit()
        except Exception as error:
            print(f'  (뒷정리 실패: {type(error).__name__})')
        finally:
            connection.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
