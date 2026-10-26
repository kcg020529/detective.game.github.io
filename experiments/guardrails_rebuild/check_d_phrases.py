"""D의 페르소나 파일에 있는 실제 문구를 출력 가드에 그대로 넣어 본다. LLM·네트워크 호출 없음. pyyaml이 필요하다(D의 prompt_render도 쓴다).

왜 필요한가
  평가셋의 정상 응답은 AI(내가)가 쓴 문장이라 D의 실제 말투와 다르다. D가 정한 문구(모름·접근 불가·게임 무관)와 말투 예시를
  가드에 넣어, 서비스에서 실제로 나올 문장이 로그나 차단에 걸리는지 본다. 규칙이나 임계값은 이 결과를 보고 고치지 않았다.

  python3 -I experiments/guardrails_rebuild/check_d_phrases.py            # enforce 기준 판정
  python3 -I experiments/guardrails_rebuild/check_d_phrases.py --mode shadow

질문은 문구에 어울리는 대표 질문 하나로 고정했고, 허용 기록은 T01-dialogue-001 하나, 역할 std, Day 2로 고정했다(결과가 재현되도록).
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from output_guard import OutputGuard, load_config  # noqa: E402

REPO = HERE.parents[1]
PERSONAS = REPO / "backend" / "character_ai" / "personas" / "personas.yaml"
RECORDS = REPO / "data" / "test-data" / "records.json"
FIX = HERE / "data" / "output_fixtures.json"
FIXED_Q = {"unknown_style": "AI-5랑 무슨 얘기 했어?", "restricted_style": "3회차 점수 알려줘", "off_topic_style": "오늘 날씨 어때?"}
EXAMPLE_Q = "어제 어디에 있었어?"
ALLOWED = ["T01-dialogue-001"]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", choices=["shadow", "enforce"], default="enforce")
    a = ap.parse_args()
    try:
        import yaml
    except ImportError:
        sys.exit("pyyaml이 필요합니다: pip install pyyaml")
    if not PERSONAS.is_file():
        sys.exit(f"{PERSONAS.relative_to(REPO)} 가 없습니다. 저장소 최상위에서 실행했는지 확인하세요.")
    personas = yaml.safe_load(PERSONAS.read_text(encoding="utf-8"))["personas"]
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    guard = OutputGuard(load_config(None, {"mode": a.mode}), records=json.loads(RECORDS.read_text(encoding="utf-8")),
                        prompt_sentences=fx["prompt_sentences"])

    groups = {"고정·참고 문구": [], "말투 예시": []}
    for p in personas:
        for key, q in FIXED_Q.items():
            groups["고정·참고 문구"].append((p["id"], key, p[key], q))
        for e in p.get("examples", []):
            groups["말투 예시"].append((p["id"], f"예시/{e['kind']}", e["a"], EXAMPLE_Q))

    print(f"== D의 실제 문구를 출력 가드에 넣은 결과 | mode={a.mode} | 허용 기록 {ALLOWED} | 문구는 personas.yaml 그대로 ==")
    for name, items in groups.items():
        rows = []
        for pid, kind, text, q in items:
            r = guard.check(text, user_input=q, role="std", day=2, target_ai=pid, allowed_context_ids=ALLOWED)
            rows.append((pid, kind, text, r))
        blocked = [x for x in rows if x[3]["decision"] != "allow"]
        logged = [x for x in rows if x[3]["decision"] == "allow" and x[3]["event"] != "none"]
        clean = len(rows) - len(blocked) - len(logged)
        print(f"\n[{name}] {len(rows)}개: 아무 기록 없이 통과 {clean} / 통과+로그 {len(logged)} / 차단 {len(blocked)}")
        for pid, kind, text, r in blocked + logged:
            sc = ", ".join(f"{c['name']}={c['score']}" for c in r["checks"] if c["level"] != "pass")
            print(f"  {r['decision']:<5} {pid} {kind:<16} {sc:<18} {text[:34]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
