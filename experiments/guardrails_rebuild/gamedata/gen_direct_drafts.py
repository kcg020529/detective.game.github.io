"""출력 가드 단독 평가용 초안을 새로 만든다. Planner·검색·입력 가드·서버를 거치지 않는다.

acl_off 수집본(runs/acl_off.jsonl)에서 질문과 '전달된 기록 ID'만 고정 입력으로 읽는다.
기록은 DB의 전체 필드(ACL 없음)로 [기억]을 만들어 D의 프롬프트(render_actor_prompt)와 LLM(chat_json)을 직접 호출한다.
결과는 acl_off와 같은 형식(config=direct_off)이라 rerun_guard.py와 run_compare.py가 그대로 쓴다.

실행 (저장소 최상위, DeepSeek 호출이 문항 수만큼 든다)
    .venv/bin/python experiments/guardrails_rebuild/gamedata/gen_direct_drafts.py --repo . --runs runs/acl_off.jsonl --out runs/direct_off.jsonl
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PERSONA = 'YB-1'  # 평가셋은 YB-1 하나로 고정


def load_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines() if line.strip()]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--repo', default='.')
    ap.add_argument('--runs', required=True, help='질문과 전달 기록 ID를 읽을 acl_off 수집본')
    ap.add_argument('--out', default='runs/direct_off.jsonl')
    ap.add_argument('--dataset', default='test-data')
    ap.add_argument('--limit', type=int, default=0, help='0이면 전부')
    ap.add_argument('--resume', action='store_true', help='--out에 이미 응답이 있는 문항은 건너뛰고 나머지(실패 포함)만 다시 호출한다')
    ap.add_argument('--max-fail', type=int, default=5, help='연달아 이만큼 실패하면 멈춘다')
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    sys.path.insert(0, str(repo))
    from backend.api.db import connect_db
    from backend.api.guard_catalog import load_catalog
    from backend.character_ai.llm_client import LLMError, chat_json
    from backend.character_ai.prompt_render import render_actor_prompt
    from backend.rag.index import load_env
    from backend.rag.service import build_memory

    env_file = repo / 'infrastructure/docker/.env'
    if env_file.exists():
        load_env(str(env_file))

    rows = [r for r in load_jsonl(Path(args.runs)) if r.get('draft')]
    if args.limit:
        rows = rows[:args.limit]
    kept = []
    out = Path(args.out)
    if args.resume and out.exists():
        kept = [r for r in load_jsonl(out) if r.get('draft')]
        done = {r['case_id'] for r in kept}
        rows = [r for r in rows if r['case_id'] not in done]
    print(f'실행 계획: {len(rows)}건 | D 프롬프트 직접 호출 | 기록 {args.dataset} 전체 필드(ACL 없음) | 연속 {args.max_fail}건 실패 시 중단', flush=True)

    connection = connect_db()
    try:
        catalog = {r['record_id']: r for r in load_catalog(connection, args.dataset)}
    finally:
        connection.close()

    results, failures, tokens = list(kept), 0, 0
    for index, row in enumerate(rows, 1):
        ids = row.get('delivered_record_ids') or []
        memory, _ = build_memory([catalog[i] for i in ids if i in catalog])
        mode = 'answer' if memory else 'unknown'
        entry = {'case_id': row['case_id'], 'config': 'direct_off', 'day': row['day'], 'category': row['category'],
                 'question': row['question'], 'delivered_record_ids': ids, 'route': 'direct',
                 'draft_type': 'normal' if mode == 'answer' else 'unknown',
                 'guard': {'decision': 'allow', 'applied': 'allow', 'reasons': []}}
        try:
            prompt = render_actor_prompt(PERSONA, mode, memory=memory if mode == 'answer' else [], history=[])
            result = chat_json(prompt, row['question'])
            reply = result['data']['reply']
            tokens += (result.get('usage') or {}).get('total_tokens', 0)
            entry.update(draft=reply, content=reply, response_type=entry['draft_type'])
            failures = 0
        except (LLMError, KeyError, ValueError) as error:
            entry.update(draft=None, content=None, response_type=None, error=type(error).__name__, detail=str(error)[:200])
            failures += 1
            print(f'  [{index}/{len(rows)}] {row["case_id"]} 실패: {type(error).__name__}', flush=True)
        results.append(entry)
        if index % 20 == 0 or index == len(rows):
            print(f'  {index}/{len(rows)}', flush=True)
        if failures >= args.max_fail:
            print('연속 실패가 많아 멈춥니다. 지금까지의 결과는 저장합니다.')
            break

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in results), encoding='utf-8')
    ok = sum(1 for r in results if r.get('draft'))
    print(f'저장: {out} | {len(results)}건 (응답 {ok}건) | 쓴 토큰 {tokens}')
    print('이어서: rerun_guard.py --runs ' + str(out) + ' --out runs/direct_guard.jsonl --config-name direct_guard')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
