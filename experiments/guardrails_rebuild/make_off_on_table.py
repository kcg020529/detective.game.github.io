"""출력 가드 OFF/ON 비교표를 만든다. 채점기(run_compare.py)가 낸 scored_cases.jsonl을 읽어 이름만 우리 파트에 맞게 바꾼다.

구성 이름: acl_off -> 가드레일 OFF(페르소나 프롬프트만), guard_only -> 가드레일 ON(출력 가드 적용).
두 구성에 모두 초안이 있는 문항만 짝으로 비교한다. 채점기는 건드리지 않는다.

실행:  python3 -I experiments/guardrails_rebuild/make_off_on_table.py --scored scores/guard_off_on/scored_cases.jsonl --out experiments/guardrails_rebuild/results/output_guard_off_on
"""
import argparse
import json
from pathlib import Path

OFF, ON = "acl_off", "guard_only"


def load(path):
    return [json.loads(l) for l in Path(path).read_text(encoding="utf-8").splitlines() if l.strip()]


def metrics(rows):
    attacks = [r for r in rows if r["attack"]]
    normals = [r for r in rows if r["scored_as_normal"]]
    clean = [r for r in normals if not r["draft_leaked"]]
    leaky = [r for r in rows if r["draft_leaked"]]
    c = lambda xs, f: (sum(1 for r in xs if f(r)), len(xs))
    return {
        "leak": c(rows, lambda r: r["leaked"]),
        "attack": c(attacks, lambda r: r["attack_success"]),
        "blocked": c(leaky, lambda r: r["leak_blocked"]),
        "fb_clean": c(clean, lambda r: r["false_block"]),
        "fb_all": c(normals, lambda r: r["false_block"]),
        "acc": c(normals, lambda r: r["correct"]),
    }


def pct(v):
    hit, total = v
    return f"{hit / total * 100:.1f}% ({hit}/{total})" if total else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scored", required=True)
    ap.add_argument("--out", required=True, help="확장자 없는 출력 경로(.md와 .html을 만든다)")
    a = ap.parse_args()
    rows = load(a.scored)
    by = {c: {r["case_id"]: r for r in rows if r["config"] == c} for c in (OFF, ON)}
    ids = sorted(set(by[OFF]) & set(by[ON]))
    off = metrics([by[OFF][i] for i in ids])
    on = metrics([by[ON][i] for i in ids])
    attacks = off["attack"][1]
    normals = off["acc"][1]

    # (지표 이름, 가드 OFF 값, 가드 ON 값, 설명)
    table = [
        ("공격 질문 유출 성공률 ↓", pct(off["attack"]), pct(on["attack"]), "권한 밖 정보를 달라는 공격 질문에서 최종 답에 유출이 남은 비율"),
        ("최종 답변 유출률 ↓", pct(off["leak"]), pct(on["leak"]), "전체 질문에서 사용자에게 간 답에 권한 밖 내용이 남은 비율"),
        ("유출 초안 차단율 ↑", "- (가드 없음)", pct(on["blocked"]), "유출이 들어 있던 초안 중 가드가 막은 비율"),
        ("정상 응답 오차단율 ↓", pct(off["fb_clean"]), pct(on["fb_clean"]), "문제없이 쓴 정상 초안 중 사용자에게 가지 못한 비율 (가드가 만든 오차단)"),
        ("정상 질문 정답률 ↑", pct(off["acc"]), pct(on["acc"]), "허용된 내용을 근거와 함께 답한 비율. 오차단이 늘면 같이 떨어진다"),
    ]
    head = ["지표", "가드레일 OFF (페르소나 프롬프트만)", "가드레일 ON (출력 가드 적용)"]

    note = (f"같은 문항 {len(ids)}개(공격 {attacks}, 정상 {normals})를 짝으로 비교했다. ACL은 두 구성 모두 사용하지 않았다. "
            "응답은 D 페르소나 프롬프트로 만든 초안이며, 가드 ON은 같은 초안에 출력 가드를 enforce로 적용한 결과다. "
            f"정상 질문 {normals}건 중 초안에 이미 권한 밖 내용이 있던 것은 {normals - off['fb_clean'][1]}건이라 오차단은 깨끗한 초안 {off['fb_clean'][1]}건을 기준으로 센다. "
            "대상은 YB-1·학부 연구생(std) 한 역할이고, 정상 질문은 모두 '가려진 원문을 달라는' 유형이다.")

    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    md = ["# 출력 가드 OFF vs ON (ACL 없음)", "", note, "", "| " + " | ".join(head) + " |", "|---|---:|---:|"]
    md += [f"| {n} | {x} | {y} |" for n, x, y, _ in table]
    md += ["", "## 지표 설명", ""] + [f"- **{n}**: {d}" for n, _, _, d in table]
    out.with_suffix(".md").write_text("\n".join(md) + "\n", encoding="utf-8")

    rows_html = "".join(f"<tr><td>{n}<small>{d}</small></td><td>{x}</td><td>{y}</td></tr>" for n, x, y, d in table)
    html = f"""<!doctype html><html lang="ko"><meta charset="utf-8"><title>출력 가드 OFF vs ON</title>
<style>body{{font:15px/1.6 system-ui;background:#1b1b1b;color:#eee;max-width:820px;margin:32px auto;padding:0 16px}}
table{{border-collapse:collapse;width:100%}}th,td{{padding:10px 8px;border-bottom:1px solid #333;text-align:right}}
th:first-child,td:first-child{{text-align:left}}small{{display:block;color:#999;font-size:12px}}p{{color:#bbb}}</style>
<h2>출력 가드 OFF vs ON (ACL 없음)</h2>
<table><tr>{''.join(f'<th>{h}</th>' for h in head)}</tr>{rows_html}</table><p>{note}</p></html>"""
    out.with_suffix(".html").write_text(html, encoding="utf-8")
    print("\n".join(md[:12]))


if __name__ == "__main__":
    main()
