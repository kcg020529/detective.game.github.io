"""Output Guard 평가 실행기. LLM·네트워크 호출 없음. 표준 라이브러리만 사용한다.

예)
  python3 -I experiments/guardrails_rebuild/run_output_eval.py --split tune --sweep     # 임계값 조정용(tune만)
  python3 -I experiments/guardrails_rebuild/run_output_eval.py --split test             # 최종 평가(임계값을 정한 뒤 한 번)
  python3 -I experiments/guardrails_rebuild/run_output_eval.py --split all --cases data/output_cases.jsonl data/output_cases_v2.jsonl

주의: --split test 결과를 보고 임계값을 고치면 test가 오염된다. 고치려면 새 케이스 묶음을 만들어 다시 잰다.
"""
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from backend.guardrails.output import OutputGuard, load_config  # noqa: E402
from backend.guardrails.output.guard import SCORED  # noqa: E402

RECORDS = HERE.parents[1] / "data" / "test-data" / "records.json"
FIX = HERE / "data" / "output_fixtures.json"
SCORE_POS = {  # 점수형 검사 → 이 검사가 잡아야 하는 check_type
    "context_leak": {"unauthorized_context"},
    "prompt_leak": {"prompt_leak"},
    "degenerate": {"degenerate"},
    "irrelevant": {"offtopic_answer", "irrelevant_answer", "appended_irrelevant"},
}


def load_cases(paths, split):
    fx = json.loads(FIX.read_text(encoding="utf-8"))["placeholders"]

    def sub(v):
        if isinstance(v, str):
            for k, x in fx.items():
                v = v.replace(k, x)
            return v
        if isinstance(v, list):
            return [sub(i) for i in v]
        return v

    rows = []
    for p in paths:
        for line in Path(p).read_text(encoding="utf-8").splitlines():
            if line.strip():
                r = {k: sub(v) for k, v in json.loads(line).items()}
                r["_file"] = Path(p).name
                if split == "all" or r["split"] == split:
                    rows.append(r)
    return rows


def wilson_upper(k, n, z=1.96):
    """k/n 비율의 95% 신뢰구간 상한(Wilson). 표본이 작을수록 넓게 나온다."""
    if n == 0:
        return float("nan")
    p = k / n
    return (p + z * z / (2 * n) + z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5)) / (1 + z * z / n)


CLOSED_SET = {"canary_exact", "synthetic_pii"}  # 값이 정해진 항목(Canary·키·개인정보): 따로 세어 보여 준다


def pct(a, b):
    return f"{a}/{b} ({a / b * 100:.1f}%)" if b else "0/0"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cases", nargs="+", default=[str(HERE / "data" / "output_cases.jsonl")],
                    help="기본은 v1만. v2는 data/output_cases_v2.jsonl 을 지정")
    ap.add_argument("--split", choices=["tune", "test", "all"], default="tune")
    ap.add_argument("--config", default=None)
    ap.add_argument("--mode", choices=["shadow", "enforce"], default="enforce",
                    help="평가는 판정(decision)을 보므로 기본 enforce. shadow는 로그 동작 확인용")
    ap.add_argument("--sweep", action="store_true", help="점수형 검사의 임계값 스윕표(0.05 단위)")
    ap.add_argument("--set", nargs="*", default=[], help="설정 덮어쓰기: thresholds.context_leak.high=0.5")
    ap.add_argument("--json", default=None, help="사례별 결과를 JSON으로 저장")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()

    ov = {"mode": a.mode}
    for kv in a.set:
        k, v = kv.split("=", 1)
        ov[k] = json.loads(v)
    cfg = load_config(a.config, ov)
    records = json.loads(RECORDS.read_text(encoding="utf-8")) if RECORDS.is_file() else []
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    guard = OutputGuard(cfg, records=records, prompt_sentences=fx["prompt_sentences"])
    cases = load_cases(a.cases, a.split)
    if not cases:
        print("케이스 없음")
        return 1

    res = []
    for c in cases:
        r = guard.check(c["response_text"], user_input=c["user_input"], role=c["role"], day=c["day"],
                        target_ai=c["target_ai"], allowed_context_ids=c["allowed_context_ids"])
        leaked = [s for s in c["must_not_contain"] if s in r["text"]]
        res.append({"case": c, "r": r, "leaked_after": leaked})

    # --- 요약 ---
    exp_bad = [x for x in res if x["case"]["expected_action"] in ("block", "mask")]
    exp_ok = [x for x in res if x["case"]["expected_action"] == "allow"]
    detected = [x for x in exp_bad if x["r"]["decision"] != "allow"]
    exact = [x for x in res if x["r"]["decision"] == x["case"]["expected_action"]]
    fp = [x for x in exp_ok if x["r"]["decision"] != "allow"]
    gray_ok = [x for x in exp_ok if x["r"]["decision"] == "allow" and x["r"]["event"] == "log"]
    residual = [x for x in res if x["leaked_after"] and x["r"]["applied"] != "block"]
    lost = [x for x in res if x["case"]["expected_action"] in ("allow", "mask") and x["r"]["decision"] in ("allow", "mask")
            and any(m not in x["r"]["text"] for m in x["case"]["must_contain"])]
    ev_ok = [x for x in res if x["r"]["event"] == x["case"]["expected_event"]]
    lat = sorted(x["r"]["latency_ms"] for x in res)

    print(f"== Output Guard 평가 | split={a.split} | 케이스 {len(res)}건 | mode={a.mode} ==")
    print(f"판정 일치(allow/mask/block): {pct(len(exact), len(res))}")
    print(f"이벤트 일치: {pct(len(ev_ok), len(res))}")
    print(f"막아야 할 것 중 잡은 비율(1-FNR): {pct(len(detected), len(exp_bad))}")
    print(f"정상 응답 오차단(FPR): {pct(len(fp), len(exp_ok))}   | 회색지대(통과+로그): {pct(len(gray_ok), len(exp_ok))}")
    if exp_ok:
        n = len(exp_ok)
        print(f"  정상 {n}건에서 오탐 {len(fp)}건 → 오탐률 95% 상한(Wilson) 약 {wilson_upper(len(fp), n) * 100:.1f}%  "
              "(합격선은 두지 않는다. 표본이 작을수록 이 숫자의 오차 범위가 넓다)")
    closed = [x for x in exp_bad if x["case"]["check_type"] in CLOSED_SET]
    closed_miss = [x for x in closed if x["r"]["decision"] == "allow"]
    print(f"닫힌 집합(Canary·키·개인정보) 놓침: {len(closed_miss)}/{len(closed)}")
    print(f"차단·마스킹 후에도 must_not_contain이 남은 건: {len(residual)}   | 통과·마스킹 후 정상 단서(must_contain)가 사라진 건: {len(lost)}")
    print(f"지연(ms) p50={lat[len(lat) // 2]:.3f}  p95={lat[int(len(lat) * 0.95) - 1] if len(lat) > 1 else lat[0]:.3f}  max={lat[-1]:.3f}")

    by_type = defaultdict(list)
    for x in res:
        by_type[x["case"]["check_type"]].append(x)
    print("\n-- 점검 유형별 (기대 → 실제) --")
    print(f"{'유형':<22}{'건수':>4}  {'일치':>5}  실제 분포")
    for t in sorted(by_type):
        xs = by_type[t]
        ok = sum(1 for x in xs if x["r"]["decision"] == x["case"]["expected_action"])
        dist = Counter(f"{x['case']['expected_action']}→{x['r']['decision']}" for x in xs)
        print(f"{t:<22}{len(xs):>4}  {ok:>3}/{len(xs):<2} " + ", ".join(f"{k}:{v}" for k, v in sorted(dist.items())))

    bad = [x for x in res if x["r"]["decision"] != x["case"]["expected_action"] or
           (x["leaked_after"] and x["r"]["applied"] != "block")]
    if bad and not a.quiet:
        print("\n-- 기대와 다른 사례 --")
        for x in bad:
            c, r = x["case"], x["r"]
            sc = ", ".join(f"{k['name']}={k['score']}({k['level']})" for k in r["checks"] if k["level"] != "pass")
            print(f"{c['case_id']} [{c['split']}/{c['check_type']}] 기대={c['expected_action']} 실제={r['decision']} | {sc or '탐지 없음'}")
    if not a.quiet:
        grays = [x for x in res if x["r"]["gray"]]
        if grays:
            print("\n-- 회색지대에 걸린 사례 (통과 + 로그) --")
            for x in grays:
                c, r = x["case"], x["r"]
                print(f"{c['case_id']} [{c['check_type']}] 기대={c['expected_action']} 실제={r['decision']} gray={r['gray']}")

    if a.sweep:
        print("\n-- 점수형 검사 임계값 스윕 (점수 ≥ t 이면 차단으로 본 경우) --")
        for name in SCORED:
            pos = [x for x in res if x["case"]["check_type"] in SCORE_POS[name] and x["case"]["expected_action"] == "block"]
            neg = [x for x in res if x["case"]["expected_action"] == "allow"]
            sp = sorted(next(k["score"] for k in x["r"]["checks"] if k["name"] == name) for x in pos)
            sn = sorted(next(k["score"] for k in x["r"]["checks"] if k["name"] == name) for x in neg)
            print(f"\n[{name}] 양성 {len(sp)}건 점수: {sp}")
            print(f"[{name}] 정상 {len(sn)}건 점수 중 상위 5개: {sn[-5:]}")
            if not sp:
                print("  → 이 분할에 양성 케이스가 없어 임계값을 정할 수 없음")
                continue
            print(f"  {'t':>5} {'FNR':>12} {'FPR':>12}")
            for i in range(1, 21):
                t = i * 0.05
                fn = sum(1 for s in sp if s < t)
                fpn = sum(1 for s in sn if s >= t)
                print(f"  {t:>5.2f} {pct(fn, len(sp)):>12} {pct(fpn, len(sn)):>12}")

    if a.json:
        out = [{"case_id": x["case"]["case_id"], "split": x["case"]["split"], "check_type": x["case"]["check_type"],
                "expected": x["case"]["expected_action"], "decision": x["r"]["decision"], "event": x["r"]["event"],
                "reasons": x["r"]["reasons"], "gray": x["r"]["gray"],
                "scores": {k["name"]: k["score"] for k in x["r"]["checks"]}} for x in res]
        Path(a.json).write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n결과 저장: {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
