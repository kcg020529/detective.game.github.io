"""같은 응답을 Output Guard의 shadow / enforce로 돌려 판정(decision)과 적용(applied)이 어떻게 다른지 보여 주는 시연 스크립트.

LLM·네트워크 없이 평가용 모의 응답(output_cases_v2.jsonl)을 쓴다. Canary·API Key 사례는 제외한다.
실행:  python3 -I experiments/guardrails_rebuild/demo_modes.py [--md 결과파일.md]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.guardrails.output import OutputGuard, load_config  # noqa: E402

DATA = ROOT / "experiments" / "guardrails_rebuild" / "data"
RECORDS = json.loads((ROOT / "data" / "test-data" / "records.json").read_text(encoding="utf-8"))
FIX = json.loads((DATA / "output_fixtures.json").read_text(encoding="utf-8"))


def picks():
    seen = set()
    for line in (DATA / "output_cases_v2.jsonl").read_text(encoding="utf-8").splitlines():
        c = json.loads(line)
        t = c["check_type"]
        if "canary" in t or "api_key" in t or t in seen:
            continue
        seen.add(t)
        yield c


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--md", help="결과를 마크다운 표로 저장할 경로")
    a = ap.parse_args()
    guards = {m: OutputGuard(load_config(None, {"mode": m}), records=RECORDS, prompt_sentences=FIX["prompt_sentences"])
              for m in ("shadow", "enforce")}
    rows = []
    for c in picks():
        row = {"type": c["check_type"], "expected": c["expected_action"], "q": c["user_input"], "resp": c["response_text"]}
        for m, g in guards.items():
            r = g.check(c["response_text"], user_input=c["user_input"], role=c["role"], day=c["day"],
                        target_ai=c["target_ai"], allowed_context_ids=c["allowed_context_ids"])
            row[m] = (r["decision"], r["applied"], r["text"])
        rows.append(row)
        print(f"\n## {row['type']} (기대 {row['expected']}) 질문: {row['q']}\n   원 응답: {row['resp'][:70]}")
        for m in guards:
            d, ap_, t = row[m]
            print(f"   [{m:7}] 판정={d:5} 적용={ap_:5} 사용자에게→ {t[:60]}")
    if a.md:
        out = ["# Output Guard shadow vs enforce 시연", "",
               "모의 응답(`output_cases_v2.jsonl`)을 같은 규칙으로 두 모드에 돌린 결과. 실제 DeepSeek 응답이 아니며 Canary·API Key 사례는 제외했다.", "",
               "| 사례 | 기대 | shadow 판정/적용 | enforce 판정/적용 | enforce에서 사용자에게 간 문장 |", "|---|---|---|---|---|"]
        for r in rows:
            cell = lambda m: f"{r[m][0]}/{r[m][1]}"
            out.append(f"| {r['type']} | {r['expected']} | {cell('shadow')} | {cell('enforce')} | {r['enforce'][2][:50].replace('|', '/')} |")
        Path(a.md).write_text("\n".join(out) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
