"""출력 가드레일 사례집(HTML)을 만든다. LLM·네트워크 호출 없음. 표준 라이브러리만 사용한다.

평가셋 191건(v1 59 + v2 132)을 지금 가드에 그대로 돌려, 사례마다
  넣은 것(질문·응답·허용 기록) → 가드가 본 것(검사별 점수·근거) → 판정 → 사용자에게 가는 문장
을 한 화면에서 볼 수 있게 한다. 숫자 요약은 화면 안에서 이 사례들로부터 계산한다.

예)
  python3 -I experiments/guardrails_rebuild/build_case_report.py --out output_guard_case_report.html --standalone
  python3 -I experiments/guardrails_rebuild/build_case_report.py --out page.html          # 아티팩트 게시용(문서 뼈대 없음)
  python3 -I experiments/guardrails_rebuild/build_case_report.py --extra-cases data/generated/normal_acl.jsonl data/generated/attack_vulnerable.jsonl --out report_with_deepseek.html --standalone
                                                                                           # gen_output_samples.py 로 만든 실제 응답을 같은 화면에 더한다
  python3 -I experiments/guardrails_rebuild/build_case_report.py --dump-json cases.json   # 데이터만 저장

규칙·임계값을 고친 뒤 다시 실행하면 화면이 새 결과로 바뀐다.
'조정 전(첫 실행)' 비교값은 results/baseline_first_run/ 의 JSON에서 읽는다. 없으면 비교 없이 표시한다.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[1]))
from backend.guardrails.output import OutputGuard, load_config  # noqa: E402

RECORDS = HERE.parents[1] / "data" / "test-data" / "records.json"
FIX = HERE / "data" / "output_fixtures.json"
CASE_FILES = [("v1", HERE / "data" / "output_cases.jsonl"), ("v2", HERE / "data" / "output_cases_v2.jsonl")]
BASELINES = {  # (묶음, split) → 첫 실행 결과 JSON
    ("v1", "test"): HERE / "results" / "baseline_first_run" / "first_run_v1_test.json",
    ("v2", "test"): HERE / "results" / "baseline_first_run" / "first_run_v2_test.json",
}
TEMPLATE = HERE / "case_report" / "template.html"
NOTES = HERE / "case_report" / "notes.json"


def substitute(fixtures: dict):
    def sub(v):
        if isinstance(v, str):
            for k, x in fixtures.items():
                v = v.replace(k, x)
            return v
        if isinstance(v, list):
            return [sub(i) for i in v]
        return v
    return sub


INPUT_DIR = HERE / "data"


def input_plan(scenarios):
    """시나리오마다, 실제 DeepSeek로 응답을 받을 입력 평가셋(파일·group)과 건수를 센다."""
    plan = {}
    for sc in scenarios:
        specs, total = [], 0
        for spec in sc.get("input", []):
            path = INPUT_DIR / f"{spec['file']}.jsonl"
            by = {}
            if path.is_file():
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        r = json.loads(line)
                        if not spec.get("groups") or r.get("group") in spec["groups"]:
                            by[r.get("group")] = by.get(r.get("group"), 0) + 1
            n = sum(by.values())
            total += n
            specs.append({"file": spec["file"], "groups": spec.get("groups"), "n": n, "byGroup": by})
        cmds = []
        for sp in specs:
            for cfg in sc.get("configs", []):
                grp = (" --group " + " ".join(sp["groups"])) if sp["groups"] else ""
                cmds.append(f"python3 -I experiments/guardrails_rebuild/gen_output_samples.py --source {sp['file']}{grp} "
                            f"--config {cfg} --out experiments/guardrails_rebuild/data/generated/{sc['id']}_{sp['file']}_{cfg}.jsonl")
        plan[sc["id"]] = {"inputs": specs, "inputTotal": total, "commands": cmds}
    return plan


def scenario_resolver(notes):
    scs = notes.get("scenarios", [])
    by_type = {t: sc["id"] for sc in scs for t in sc.get("types", [])}
    leak_types = set(notes.get("leakTypes", []))
    over = notes.get("scenarioOverrides", {})
    origin = {}
    for sc in scs:
        for spec in sc.get("input", []):
            for g in (spec.get("groups") or [None]):
                origin[(spec["file"], g)] = sc["id"]

    def resolve(c, in_file, in_group):
        if c["id"] in over:
            return over[c["id"]]
        if in_file:  # DeepSeek로 만든 응답은 어떤 입력에서 나왔는지로 나눈다
            return origin.get((in_file, in_group)) or origin.get((in_file, None)) or "normal"
        if c["exp"] == "allow" and c["type"] in leak_types:
            return "risky_ok"  # 유출 유형처럼 보이지만 정상인 질문(예: '예시로 든 키 있어?')
        return by_type.get(c["type"], "normal")
    return resolve


def load_cases_file(path: Path, ds: str, sub, guard, baseline):
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        c = {k: sub(v) for k, v in json.loads(line).items()}
        r = guard.check(c["response_text"], user_input=c["user_input"], role=c["role"], day=c["day"],
                        target_ai=c["target_ai"], allowed_context_ids=c["allowed_context_ids"])
        b = baseline.get((ds, c["case_id"]))
        out.append({
            "id": c["case_id"], "ds": ds, "split": c["split"], "type": c["check_type"],
            "role": c["role"], "day": c["day"], "ai": c["target_ai"],
            "q": c["user_input"], "resp": c["response_text"], "allowed": c["allowed_context_ids"],
            "exp": c["expected_action"], "expEvent": c["expected_event"],
            "mustNot": c.get("must_not_contain", []), "must": c.get("must_contain", []),
            "leaked": c.get("leaked_record_ids", []), "note": c.get("notes", ""),
            "review": c.get("review", ""), "source": c.get("source", ""),
            "inFile": c.get("input_file"), "inGroup": c.get("input_group"),
            "res": {
                "dec": r["decision"], "applied": r["applied"], "text": r["text"], "event": r["event"],
                "reasons": r["reasons"], "gray": r["gray"],
                "checks": [{"n": k["name"], "s": k["score"], "l": k["level"], "d": k["detail"]} for k in r["checks"]],
            },
            "base": ({"dec": b["decision"], "event": b["event"], "reasons": b["reasons"], "gray": b["gray"],
                      "scores": b["scores"]} if b else None),
        })
    return out


def collect(extra_cases=()) -> dict:
    fx = json.loads(FIX.read_text(encoding="utf-8"))
    sub = substitute(fx["placeholders"])
    cfg = load_config(None, {"mode": "enforce"})  # 평가는 판정(decision)을 보므로 enforce
    records = json.loads(RECORDS.read_text(encoding="utf-8"))
    guard = OutputGuard(cfg, records=records, prompt_sentences=fx["prompt_sentences"])

    baseline = {}
    for key, path in BASELINES.items():
        if path.is_file():
            for r in json.loads(path.read_text(encoding="utf-8")):
                baseline[(key[0], r["case_id"])] = r

    cases = []
    for ds, path in CASE_FILES:
        cases += load_cases_file(path, ds, sub, guard, baseline)
    for path in extra_cases:  # gen_output_samples.py 로 만든 실제 DeepSeek 응답 등
        cases += load_cases_file(Path(path), "gen", sub, guard, baseline)

    seen = set()
    for c in cases:
        if c["id"] in seen:
            sys.exit(f"사례 번호가 겹칩니다: {c['id']} (같은 번호의 파일을 두 번 넣었거나 예전 방식으로 만든 파일일 수 있음). 해당 파일을 gen_output_samples.py 로 다시 만드세요.")
        seen.add(c["id"])

    notes = json.loads(NOTES.read_text(encoding="utf-8")) if NOTES.is_file() else {}
    resolve = scenario_resolver(notes)
    for c in cases:
        c["scn"] = resolve(c, c.pop("inFile"), c.pop("inGroup"))
    return {
        "scenarios": [dict(sc, **input_plan(notes.get("scenarios", []))[sc["id"]]) for sc in notes.get("scenarios", [])],
        "thresholds": cfg["thresholds"],
        "fallback": cfg["fallback"],
        "mode_note": "평가는 enforce로 돌렸다(운영 기본값은 shadow).",
        "records": records,
        "promptSentences": fx["prompt_sentences"],
        "secrets": {"canary": cfg["secrets"]["canary"], "api_keys": cfg["secrets"]["api_keys"],
                    "pii_values": cfg["secrets"]["pii_values"]},
        "cases": cases,
        "notes": notes,
    }


def render(data: dict, standalone: bool) -> str:
    html = TEMPLATE.read_text(encoding="utf-8")
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    html = html.replace("/*__DATA__*/null", payload)
    if standalone:
        html = ('<!doctype html>\n<html lang="ko">\n<head>\n<meta charset="utf-8">\n'
                '<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n</head>\n<body>\n'
                + html + "\n</body>\n</html>\n")
    return html


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="output_guard_case_report.html")
    ap.add_argument("--standalone", action="store_true", help="<html> 뼈대까지 붙여 브라우저에서 바로 열 수 있게 한다")
    ap.add_argument("--dump-json", default=None, help="화면 대신 사례별 결과 JSON만 저장")
    ap.add_argument("--extra-cases", nargs="*", default=[], help="gen_output_samples.py 로 만든 JSONL(실제 응답)을 더한다")
    a = ap.parse_args()
    data = collect(a.extra_cases)
    if a.dump_json:
        Path(a.dump_json).write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"저장: {a.dump_json} ({len(data['cases'])}건)")
        return 0
    out = Path(a.out)
    out.write_text(render(data, a.standalone), encoding="utf-8")
    print(f"저장: {out} ({len(data['cases'])}건, {out.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
