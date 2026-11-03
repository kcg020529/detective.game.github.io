"""가드 적용 전(초안)과 후(사용자에게 간 문장)를 YB-1 사례로 나란히 보여 준다. 규칙 기반이라 LLM·DB 호출이 없다.

실행:  python3 -I experiments/guardrails_rebuild/show_before_after.py --runs runs/guard_only.jsonl [--limit 3]
"""
import argparse
import json
from pathlib import Path

# 채점 기준: 공격은 denied_*, future_day, injection. withheld_*는 허용 범위만 답해야 하는 정상 질문이다.
ATTACK = ("denied_", "future_day", "injection")


def show(title, rows, limit):
    print(f"\n==== {title} ({len(rows)}건 중 {min(limit, len(rows))}건) ====")
    for r in rows[:limit]:
        g = r["guard"]
        print(f"\n[{r['category']}] 질문: {r['question']}")
        print(f"  가드 전(초안): {r['draft'][:110]}")
        print(f"  가드 후(전달): {r['content'][:110]}")
        print(f"  판정={g['decision']} 적용={g['applied']} 사유={g['reasons']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", required=True)
    ap.add_argument("--limit", type=int, default=3)
    a = ap.parse_args()
    rows = [json.loads(l) for l in Path(a.runs).read_text(encoding="utf-8").splitlines() if l.strip()]
    rows = [r for r in rows if r.get("draft")]
    is_attack = lambda r: r["category"].startswith(ATTACK)
    show("막힌 공격 질문 (초안엔 있었고 가드가 막음)", [r for r in rows if is_attack(r) and r["guard"]["applied"] == "block"], a.limit)
    show("정상 질문이 그대로 통과", [r for r in rows if not is_attack(r) and r["guard"]["applied"] == "allow"], a.limit)
    show("정상 질문이 막힘 (오차단)", [r for r in rows if not is_attack(r) and r["guard"]["applied"] == "block"], a.limit)


if __name__ == "__main__":
    main()
