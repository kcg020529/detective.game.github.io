"""LLM 실제 호출 확인용 수동 스크립트. 자동 테스트가 아니며, .env의 키가 필요하고 호출마다 비용이 든다.

사용:
  python3 backend/character_ai/check_llm.py                       # AI-1~6, answer mode, 기본 질문 (호출 6회)
  python3 backend/character_ai/check_llm.py --persona AI-3 --question "그때 어디 있었어?"
  python3 backend/character_ai/check_llm.py --all-modes           # AI-1~6 x 5개 mode (LLM 호출 12회, restricted·off_topic·injection은 고정 문구라 호출 없음)
  python3 backend/character_ai/check_llm.py --all-modes --repeat 5   # 같은 호출을 5번씩 (LLM 호출 60회) 하고 자동 채점 요약
  python3 backend/character_ai/check_llm.py --all-modes --repeat 5 --verbose   # 모든 응답을 출력 (사람이 읽어 볼 때)

AI 응답은 매번 달라서 한 번 본 것으로는 판단하기 어렵다. --repeat로 여러 번 받아 eval_rules.py의 규칙으로 채점하고,
캐릭터별 요약(첫머리 반복, 말버릇 지시 이행 등)만 보면 된다. 말투가 서로 구분되는지는 출력된 답변을 사람이 읽어야 한다.

--repeat가 2 이상이면 (1) 질문을 아래 DEFAULT_QUESTIONS의 5가지 표현으로 돌려 가며 보내고(예시 질문과 우연히 같아서 생기는 착시를 줄이려고),
(2) answer mode에서는 말버릇 사용 지시를 켬/끔으로 번갈아 넣어(use_catchphrase) 지시를 따르는지 본다.
이 패턴은 검사용이다. 실제로 누가 얼마나 자주 켤지는 정하지 않았다. (prompt_render.py의 [검토15])
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from eval_rules import check_reply, summarize  # noqa: E402
from llm_client import LLMError, chat_json  # noqa: E402
from prompt_render import FIXED_MODES, MODES, fixed_reply, get_persona, persona_ids, render_actor_prompt  # noqa: E402

# 시험용 값이다. 실제 시나리오 내용이 아니다.
MEMORY = [
    {"id": "m1", "text": "(테스트용) 오전에 A구역 복도에 있었다."},
    {"id": "m2", "text": "(테스트용) 오후에는 대기실에 있었다."},
]
HISTORY = [{"speaker": "조사자", "text": "(테스트용) 안녕, 물어볼 게 있어."}]
# 모두 "오전 위치"를 묻는 표현이다. 시험용 기억 m1과 맞춘 값이고, unknown·restricted 답변에 장소 단어가 섞이지 않도록 장소 단어는 뺐다.
DEFAULT_QUESTIONS = (
    "어제 오전에 어디에 있었어?",
    "오전에는 어디에 있었는지 말해 줄래?",
    "아침 시간대에 네가 있던 곳이 어디야?",
    "어제 오전 네 위치 좀 알려 줘.",
    "오전에 어디서 뭐 하고 있었는지 기억나?",
)
REQUIRED_IN_ANSWER = ("A구역",)  # 위 질문과 시험용 기억 m1에 맞춘 값이다. 질문을 바꾸면 이 점검은 의미가 없을 수 있다.
RELEVANT_IDS = ("m1",)           # 위 질문(오전 위치)에 쓰는 것이 맞는 기억. m2(오후)를 쓰면 무관한 기억을 쓴 것이다. [검토17]
CATCH_EVERY = 2                  # --repeat 2 이상일 때 answer mode에서 이 간격으로 말버릇 사용을 켠다 (0, 2, 4번째 호출)
MAX_CONSECUTIVE_ERRORS = 3       # 연속으로 이만큼 실패하면 키나 잔액 문제로 보고 멈춘다
MAX_CALLS_WITHOUT_YES = 100
FIXED_NOTE = {"restricted": "(서버가 접근 불가로 판정)", "off_topic": "(게임과 무관한 질문으로 판정)", "injection": "(인젝션 시도로 판정)"}


def run_checks(persona_list, modes, repeat, questions, chat=chat_json, memory=None, history=None, progress=None,
               catch_every=None):
    """persona x mode x repeat 호출을 하고 채점한다. chat은 시험에서 가짜 함수로 바꿀 수 있다.

    questions: 질문 목록(호출마다 순서대로 돌려 쓴다). 문자열 하나를 줘도 된다.
    catch_every: 숫자를 주면 answer mode에서 그 간격마다 말버릇 사용을 켜고 나머지는 끈다. None이면 지시하지 않는다.
    돌려주는 값: {"results": [...], "totals": {...}, "aborted": bool}
    """
    memory = MEMORY if memory is None else memory
    history = HISTORY if history is None else history
    questions = (questions,) if isinstance(questions, str) else tuple(questions)
    memory_ids = {m["id"] for m in memory}
    results = []
    totals = {"prompt_tokens": 0, "completion_tokens": 0}
    consecutive_errors = 0
    for pid in persona_list:
        persona = get_persona(pid)
        for mode in modes:
            if mode in FIXED_MODES:
                # [검토18] LLM을 부르지 않는 고정 문구다. 매번 같으므로 한 번만 확인하고, 같은 규칙으로 점검한다.
                fixed = fixed_reply(pid, mode)
                results.append({"persona": pid, "mode": mode, "run": 1, "question": FIXED_NOTE[mode], "catch": None,
                                "reply": fixed["reply"], "used": fixed["used"], "model": "고정 문구(LLM 호출 없음)", "usage": {},
                                "problems": check_reply(persona, mode, fixed, memory_ids), "error": None, "attempts": 0,
                                "fixed": True})
                if progress:
                    progress("=")
                continue
            for i in range(repeat):
                catch = None if not catch_every else (i % catch_every == 0)
                if catch is not None and mode != "answer":
                    catch = False  # prompt_render가 answer 외에는 항상 끈다. 기록도 같게 맞춘다.
                question = questions[i % len(questions)]
                prompt = render_actor_prompt(pid, mode, memory=memory, history=history, use_catchphrase=catch)
                rec = {"persona": pid, "mode": mode, "run": i + 1, "question": question, "catch": catch,
                       "reply": "", "used": None, "problems": [], "error": None, "model": None, "usage": {},
                       "attempts": 1, "fixed": False}
                try:
                    res = chat(prompt, question)
                except LLMError as e:
                    rec["error"] = str(e)
                    rec["attempts"] = getattr(e, "attempts", 1)
                    rec["usage"] = getattr(e, "usage", {}) or {}  # 실패한 호출도 토큰은 요금에 잡힌다
                    for k in totals:
                        totals[k] += rec["usage"].get(k) or 0
                    results.append(rec)
                    consecutive_errors += 1
                    if progress:
                        progress("x")
                    if consecutive_errors >= MAX_CONSECUTIVE_ERRORS:
                        return {"results": results, "totals": totals, "aborted": True}
                    continue
                consecutive_errors = 0
                data = res["data"]
                rec.update(reply=data["reply"], used=data.get("used"), model=res.get("model"), usage=res.get("usage") or {},
                           attempts=res.get("attempts", 1))
                required = REQUIRED_IN_ANSWER if mode == "answer" else ()
                rec["problems"] = check_reply(persona, mode, data, memory_ids, required_words=required,
                                              relevant_ids=RELEVANT_IDS)
                for k in totals:
                    totals[k] += rec["usage"].get(k) or 0
                results.append(rec)
                if progress:
                    progress(".")
    return {"results": results, "totals": totals, "aborted": False}


def _catch_label(catch):
    return {True: "말버릇 켬", False: "말버릇 끔", None: ""}[catch]


def _print_one(rec):
    label = _catch_label(rec["catch"])
    if rec.get("fixed"):
        print(f"=== {rec['persona']} / {rec['mode']} / 고정 문구(LLM 호출 없음)")
        print("  reply:", rec["reply"])
        if rec["problems"]:
            print("  [점검] " + " / ".join(rec["problems"]))
        return
    retry = f" / 재시도 {rec['attempts'] - 1}회" if rec["attempts"] > 1 else ""
    print(f"=== {rec['persona']} / {rec['mode']} #{rec['run']}" + (f" / {label}" if label else "") + retry + f" / 질문: {rec['question']}")
    if rec["error"]:
        print("  [실패]", rec["error"])
        return
    print("  reply:", rec["reply"])
    print("  used :", rec["used"])
    usage = rec["usage"]
    print(f"  모델: {rec['model']} / 토큰 입력 {usage.get('prompt_tokens')} 출력 {usage.get('completion_tokens')}")
    if rec["problems"]:
        print("  [점검] " + " / ".join(rec["problems"]))


def _rate(rate, n):
    return "-" if rate is None else f"{rate:.0%}({round(rate * n)}/{n})"


def print_report(report, persona_list, repeat, verbose=False):
    results = report["results"]
    if repeat == 1 or verbose:
        for rec in results:
            _print_one(rec)
    else:
        print("\n--- 대표 답변 (캐릭터·mode별 첫 번째) ---")
        for rec in results:
            if rec["run"] == 1:
                text = f"[실패] {rec['error']}" if rec["error"] else rec["reply"]
                label = _catch_label(rec["catch"])
                print(f"[{rec['persona']} / {rec['mode']}{' / ' + label if label else ''}] {text}")

    if repeat > 1:
        personas = {pid: get_persona(pid) for pid in persona_list}
        summary = summarize(results, personas)
        print("\n--- 캐릭터별 요약 ---")
        print("캐릭터 | 호출 | 실패 | 재시도 | 규칙위반 | 최다 첫머리 (비율) | 말버릇 첫머리 | 켠 턴 사용 | 끈 턴 사용")
        for pid, s in summary.items():
            retried = sum(1 for r in results if r["persona"] == pid and r["attempts"] > 1)
            print(f"{pid} | {s['calls']} | {s['errors']} | {retried} | {s['problem_replies']} | "
                  f"{s['top_opening']!r} ({s['top_opening_rate']:.0%}) | {s['catch_start_rate']:.0%} | "
                  f"{_rate(s['catch_on_rate'], s['catch_on_n'])} | {_rate(s['catch_off_rate'], s['catch_off_n'])}")
        flagged = {pid: s["flags"] for pid, s in summary.items() if s["flags"]}
        if flagged:
            print("\n[확인 필요]")
            for pid, flags in flagged.items():
                print(f"  {pid}: " + ", ".join(flags))
        else:
            print("\n[기준 통과] 첫머리 반복, 말버릇, 규칙 위반 기준에 걸린 캐릭터가 없습니다. (기준은 임시값, eval_rules.py)")

    bad = [r for r in results if r["problems"] and not r["error"]]
    if bad:
        print(f"\n--- 규칙 위반 응답 {len(bad)}건 (최대 20건 표시) ---")
        for r in bad[:20]:
            print(f"[{r['persona']} / {r['mode']} #{r['run']}] {' / '.join(r['problems'])}")
            print(f"    질문: {r['question']}")
            print(f"    답변: {r['reply']}")
    errors = [r for r in results if r["error"]]
    llm_calls = [r for r in results if not r.get("fixed")]
    retried = [r for r in results if r["attempts"] > 1]
    if retried:
        recovered = sum(1 for r in retried if not r["error"])
        print(f"\n재시도가 필요했던 호출 {len(retried)}건 (재시도 후 성공 {recovered}건, 끝내 실패 {len(retried) - recovered}건)")
    if errors:
        print(f"\n--- 호출 실패 {len(errors)}건 (처음 3건) ---")
        for r in errors[:3]:
            print(f"[{r['persona']} / {r['mode']} #{r['run']}] {r['error']}")
    if report["aborted"]:
        print(f"\n연속 {MAX_CONSECUTIVE_ERRORS}회 실패해서 중단했습니다. 키(.env), 잔액, 모델 이름을 확인해 주세요.")

    t = report["totals"]
    print(f"\n합계 토큰(재시도로 버린 응답 포함): 입력 {t['prompt_tokens']} 출력 {t['completion_tokens']} / LLM 호출 {len(llm_calls)}회 / 실패 {len(errors)}건")
    return len(errors)


def main():
    ap = argparse.ArgumentParser(description="페르소나 프롬프트로 LLM을 실제 호출해 본다.")
    ap.add_argument("--persona", choices=persona_ids(), help="한 명만 호출 (기본: 6명 모두)")
    ap.add_argument("--mode", choices=MODES, default="answer")
    ap.add_argument("--all-modes", action="store_true", help="5개 mode를 모두 확인 (restricted, off_topic, injection은 LLM 호출 없이 고정 문구만)")
    ap.add_argument("--question", help="질문 하나로 고정 (기본: 5가지 표현을 돌려 가며 사용)")
    ap.add_argument("--repeat", type=int, default=1, help="같은 호출을 몇 번 반복할지 (1~20). 2 이상이면 자동 채점 요약을 낸다")
    ap.add_argument("--verbose", action="store_true", help="--repeat가 2 이상일 때도 모든 응답을 출력")
    ap.add_argument("--yes", action="store_true", help=f"호출이 {MAX_CALLS_WITHOUT_YES}회를 넘어도 확인 없이 실행")
    args = ap.parse_args()
    if not 1 <= args.repeat <= 20:
        ap.error("--repeat는 1~20 사이여야 합니다.")

    personas = [args.persona] if args.persona else persona_ids()
    modes = MODES if args.all_modes else (args.mode,)
    llm_modes = [m for m in modes if m not in FIXED_MODES]
    planned = len(personas) * len(llm_modes) * args.repeat  # 고정 문구 mode는 LLM을 부르지 않는다 ([검토18][검토19])
    if planned > MAX_CALLS_WITHOUT_YES and not args.yes:
        ap.error(f"호출이 {planned}회 예정입니다. 비용을 확인했다면 --yes를 붙여 다시 실행하세요.")
    if args.repeat > 1:
        print(f"LLM 호출 {planned}회를 진행합니다. 점(.)이 호출 한 번이고, 등호(=)는 호출 없는 고정 문구(restricted, off_topic, injection) 확인입니다.", file=sys.stderr)

    def progress(ch):
        print(ch, end="", file=sys.stderr, flush=True)

    questions = (args.question,) if args.question else DEFAULT_QUESTIONS
    if args.repeat == 1 and not args.question:
        questions = DEFAULT_QUESTIONS[:1]  # 한 번만 부를 때는 예전과 같은 기본 질문 하나를 쓴다
    report = run_checks(personas, modes, args.repeat, questions,
                        progress=progress if args.repeat > 1 else None,
                        catch_every=CATCH_EVERY if args.repeat > 1 else None)
    if args.repeat > 1:
        print(file=sys.stderr)
    failures = print_report(report, personas, args.repeat, verbose=args.verbose)
    sys.exit(1 if failures else 0)


if __name__ == "__main__":
    main()
