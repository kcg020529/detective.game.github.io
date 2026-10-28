"""평가셋 형식·중복·분할 점검 (v1). 표준 라이브러리만 사용한다. LLM·네트워크 호출 없음.

실행 (저장소 어디서든):
    python3 -I experiments/guardrails_rebuild/validate_data.py
오류가 있으면 종료 코드 1, 없으면 0.
"""
import json
import re
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA = HERE / "data"
RECORDS = HERE.parents[1] / "data" / "test-data" / "records.json"   # 저장소 최상위 기준
MAXLEN = 100

INPUT_FILES = ("normal", "attack", "borderline", "offtopic", "limits")
INPUT_FIELDS = ["case_id", "dataset", "split", "family_id", "text", "char_len", "lang", "role", "target_ai",
                "category", "group", "type_no", "expected_action", "expected_route", "expected_event",
                "risk_words", "source", "review", "notes"]
OUTPUT_FIELDS = ["case_id", "dataset", "split", "family_id", "check_type", "role", "day", "target_ai", "user_input",
                 "allowed_context_ids", "response_text", "expected_action", "expected_event", "must_not_contain",
                 "must_contain", "leaked_record_ids", "source", "review", "notes"]
COMMON = {
    "split": {"tune", "test"},
    "role": {"prof", "grad", "std"},
    "target_ai": {f"AI-{i}" for i in range(1, 7)},
    "review": {"unreviewed", "approved", "changed", "rejected"},
}
IN_ENUM = {
    "lang": {"ko", "en", "mixed", "other"},
    "category": {"normal", "permission", "sensitive", "injection", "offtopic"},
    "expected_action": {"allow", "caution", "block", "reject"},
    "expected_route": {"planner", "fixed_injection", "fixed_off_topic", "backend_reject"},
    "expected_event": {"none", "log", "alert"},
}
OUT_ENUM = {"expected_action": {"allow", "mask", "block"}, "expected_event": {"none", "log", "alert"}}
ROUTE_OK = {"allow": "planner", "caution": "planner", "block": "fixed_injection"}


def norm(t):
    return re.sub(r"\s+", " ", t).strip().lower()


def load(name, errors):
    path = DATA / f"{name}.jsonl"
    rows = []
    if not path.is_file():
        errors.append(f"파일 없음: {path.name}")
        return rows
    for ln, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(f"{name}:{ln} JSON 오류 {e}")
            continue
        r["_file"] = name
        rows.append(r)
    return rows


def check_enum(r, enums, errors):
    for k, allowed in enums.items():
        if r.get(k) not in allowed:
            errors.append(f"{r.get('case_id')} {k} 값 오류: {r.get(k)!r}")


def main():
    errors = []
    inp, out = [], []
    for name in INPUT_FILES:
        for r in load(name, errors):
            inp.append(r)
            miss = set(INPUT_FIELDS) - set(r)
            if miss:
                errors.append(f"{r.get('case_id')} 필드 누락 {sorted(miss)}")
                continue
            check_enum(r, COMMON, errors)
            check_enum(r, IN_ENUM, errors)
            t = r["text"]
            if not isinstance(t, str) or not t.strip():
                errors.append(f"{r['case_id']} text 비어 있음")
                continue
            if r["dataset"] != name:
                errors.append(f"{r['case_id']} dataset 값이 파일명과 다름")
            if r["char_len"] != len(t):
                errors.append(f"{r['case_id']} char_len 불일치")
            if name == "limits":
                if len(t) <= MAXLEN:
                    errors.append(f"{r['case_id']} limits 케이스인데 {MAXLEN}자 이하")
                if r["expected_route"] != "backend_reject" or r["expected_action"] != "reject":
                    errors.append(f"{r['case_id']} limits는 reject/backend_reject여야 함")
            else:
                if len(t) > MAXLEN:
                    errors.append(f"{r['case_id']} {MAXLEN}자 초과 ({len(t)}자)")
                if r["expected_action"] == "reject":
                    errors.append(f"{r['case_id']} limits 밖에서 reject 사용")
            if name == "offtopic":
                if r["expected_route"] != "fixed_off_topic" or r["category"] != "offtopic":
                    errors.append(f"{r['case_id']} offtopic은 fixed_off_topic 경로여야 함")
            elif name != "limits":
                if r["category"] == "offtopic":
                    errors.append(f"{r['case_id']} offtopic 분류는 offtopic.jsonl에만 둠")
                want = ROUTE_OK.get(r["expected_action"])
                if r["expected_route"] != want:
                    errors.append(f"{r['case_id']} 경로 불일치: {r['expected_action']} → {want}")
            if name == "normal" and (r["expected_action"] != "allow" or r["category"] != "normal"):
                errors.append(f"{r['case_id']} 정상 질문은 allow/normal이어야 함")
            if name == "attack" and r["expected_action"] == "allow":
                errors.append(f"{r['case_id']} 공격 문장인데 allow")

    records = {}
    if RECORDS.is_file():
        for x in json.loads(RECORDS.read_text(encoding="utf-8")):
            records[x["record_id"]] = x
    else:
        print(f"[경고] {RECORDS} 없음. 출력 평가셋의 허용 Context 대조를 건너뜁니다.")

    out_rows = []
    for name in sorted(p.stem for p in DATA.glob("output_cases*.jsonl")):
        out_rows += load(name, errors)
    for r in out_rows:
        out.append(r)
        miss = set(OUTPUT_FIELDS) - set(r)
        if miss:
            errors.append(f"{r.get('case_id')} 필드 누락 {sorted(miss)}")
            continue
        check_enum(r, COMMON, errors)
        check_enum(r, OUT_ENUM, errors)
        if not isinstance(r["day"], int) or not 1 <= r["day"] <= 6:
            errors.append(f"{r['case_id']} day 값 오류")
        if len(r["user_input"]) > MAXLEN:
            errors.append(f"{r['case_id']} user_input {MAXLEN}자 초과")
        if r["expected_action"] in ("block", "mask") and r["check_type"] not in ("broken_response",) and not r["must_not_contain"]:
            errors.append(f"{r['case_id']} block/mask인데 must_not_contain 없음")
        if r["expected_action"] == "allow" and r["must_not_contain"]:
            errors.append(f"{r['case_id']} allow인데 must_not_contain 있음")
        for s in r["must_not_contain"]:
            if s not in r["response_text"]:
                errors.append(f"{r['case_id']} must_not_contain {s[:20]!r}이 response_text에 없음")
        for s in r["must_contain"]:
            if s not in r["response_text"]:
                errors.append(f"{r['case_id']} must_contain {s[:20]!r}이 response_text에 없음")
        if records:
            want = sorted(k for k, v in records.items() if v["day"] <= r["day"] and r["role"] in v["allowed_roles"])
            if sorted(r["allowed_context_ids"]) != want:
                errors.append(f"{r['case_id']} allowed_context_ids가 role/day 기준과 다름")
            for rid in r["leaked_record_ids"]:
                if rid not in records:
                    errors.append(f"{r['case_id']} 없는 기록 ID {rid}")
                elif rid in r["allowed_context_ids"]:
                    errors.append(f"{r['case_id']} 유출 기록이 허용 목록에 포함됨 {rid}")

    for label, rows in (("입력", inp), ("출력", out)):
        ids = Counter(r.get("case_id") for r in rows)
        errors += [f"case_id 중복: {k}" for k, v in ids.items() if v > 1]
        fam = {}
        for r in rows:
            fam.setdefault(r.get("family_id"), set()).add(r.get("split"))
        errors += [f"{label}: 가족이 tune/test에 걸침: {k}" for k, v in fam.items() if len(v) > 1]
    texts = Counter(norm(r.get("text", "")) for r in inp)
    errors += [f"본문 중복: {k[:40]}" for k, v in texts.items() if v > 1]

    print(f"입력 {len(inp)}건 / 출력 {len(out)}건")
    for name in INPUT_FILES:
        sub = [r for r in inp if r["_file"] == name]
        print(f"  {name}: {len(sub)}건  " + "  ".join(f"{s}={sum(1 for r in sub if r['split'] == s)}" for s in ("tune", "test")))
    print(f"  output_cases: {len(out)}건  " + "  ".join(f"{s}={sum(1 for r in out if r['split'] == s)}" for s in ("tune", "test")))
    print("입력 분류별:", dict(Counter(r["category"] for r in inp)))
    print("입력 기대 대응별:", dict(Counter(r["expected_action"] for r in inp)))
    print("입력 역할별:", dict(Counter(r["role"] for r in inp)))
    ln = sorted(r["char_len"] for r in inp if r["_file"] != "limits")
    if ln:
        print(f"입력 글자 수: 중앙값 {ln[len(ln)//2]}, 최대 {ln[-1]}, 70자 이상 {sum(x >= 70 for x in ln)}건")
    print("출력 점검 유형별:", dict(Counter(r["check_type"] for r in out)))
    print("출력 기대 대응별:", dict(Counter(r["expected_action"] for r in out)))
    print("검수 상태:", dict(Counter(r["review"] for r in inp + out)))
    nt = sum(1 for r in inp if r["_file"] == "normal" and r["split"] == "test")
    if nt:
        print(f"정상 test {nt}건: 오탐 0건이어도 95% 상한(Wilson)은 약 {3.8416 / (nt + 3.8416) * 100:.1f}%. 표본이 작을수록 숫자의 오차가 크다.")

    if errors:
        print(f"\n오류 {len(errors)}건")
        for e in errors[:60]:
            print(" -", e)
        return 1
    print("\n형식·중복·분할·허용 Context 점검 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main())
