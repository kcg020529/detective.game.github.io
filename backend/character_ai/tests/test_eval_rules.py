"""eval_rules(자동 채점)와 check_llm.run_checks 테스트. 실제 API를 호출하지 않고 가짜 응답만 쓴다.

실행: python3 -I backend/character_ai/tests/test_eval_rules.py   (pytest가 있으면 pytest로도 실행된다)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import check_llm  # noqa: E402
import eval_rules as ev  # noqa: E402
from llm_client import LLMError  # noqa: E402
from prompt_render import FIXED_MODES, fixed_reply, get_persona, persona_ids  # noqa: E402

IDS = {"m1", "m2"}


def _persona(**kw):
    p = {"id": "AI-T", "catchphrase": "정확히는요…", "max_sentences": 3}
    p.update(kw)
    return p


def test_normalize_and_opening():
    assert ev.normalize("정확히는요… 어제, 오전!") == "정확히는요어제오전"
    assert ev.opening("정확히는요, 어제 오전에는") == ev.opening("정확히는요… 어제 오전에는")
    assert ev.opening("") == ""


def test_catchphrase_position():
    c = "일단 천천히 얘기해 볼까요?"
    assert ev.starts_with_catchphrase("일단 천천히 얘기해 볼까요? 말씀드릴게요.", c)
    assert not ev.starts_with_catchphrase("대기실이었어요. 일단 천천히 얘기해 볼까요?", c)
    assert ev.uses_catchphrase("대기실이었어요. 일단 천천히 얘기해 볼까요?", c)
    assert not ev.uses_catchphrase("대기실이었어요.", c)


def test_sentence_count_ignores_ellipsis():
    assert ev.sentence_count("A구역이에요. 그다음은 몰라요.") == 2
    assert ev.sentence_count("그러니까… 아마 거기였어요… 걱정되네요…") == 1
    assert ev.sentence_count("") == 0


def test_clean_replies_pass():
    p = _persona()
    assert ev.check_reply(p, "answer", {"reply": "A구역 복도에 있었어요.", "used": ["m1"]}, IDS, ("A구역",)) == []
    assert ev.check_reply(p, "unknown", {"reply": "그건 못 봤어요.", "used": []}, IDS) == []
    assert ev.check_reply(p, "restricted", {"reply": "그건 제가 볼 수 있는 자료가 아니에요.", "used": []}, IDS) == []


def _has(problems, text):
    return any(text in x for x in problems)


def test_problems_are_detected():
    p = _persona(max_sentences=2)
    assert _has(ev.check_reply(p, "answer", {"reply": "A구역이에요.", "used": ["m9"]}, IDS), "기억 번호")
    assert _has(ev.check_reply(p, "unknown", {"reply": "몰라요.", "used": ["m1"]}, IDS), "used가 비어 있지 않음")
    assert _has(ev.check_reply(p, "restricted", {"reply": "기록이 없어서 말씀드릴 수 없어요.", "used": []}, IDS), "기록·기억 유무")
    assert _has(ev.check_reply(p, "unknown", {"reply": "권한이 없어요.", "used": []}, IDS), "접근 권한")
    assert _has(ev.check_reply(p, "answer", {"reply": "Zone-A에 있었어요.", "used": ["m1"]}, IDS), "예시 속 장소")
    assert _has(ev.check_reply(p, "answer", {"reply": "m1에 있어요.", "used": ["m1"]}, IDS), "기억 번호(m1")
    assert _has(ev.check_reply(p, "answer", {"reply": "좋아요 😀", "used": ["m1"]}, IDS), "이모티콘")
    assert _has(ev.check_reply(p, "answer", {"reply": "하나. 둘. 셋.", "used": ["m1"]}, IDS), "문장 수")
    assert _has(ev.check_reply(p, "answer", {"reply": "대기실이에요.", "used": ["m2"]}, IDS, ("A구역",)), "A구역")
    assert ev.check_reply(p, "answer", {"reply": "  ", "used": []}, IDS) == ["reply가 비어 있음"]
    assert _has(ev.check_reply(p, "answer", {"reply": "네.", "used": "m1"}, IDS), "used 형식")


def test_unrelated_memory_is_caught_by_id_not_by_words():
    """질문과 무관한 기억(m2)을 쓴 응답은 답변 문장이 어떻든 used 번호로 잡힌다. (2026-10-21 AI-1에서 1/25건 나옴)"""
    p = _persona()
    both = {"reply": "오전엔 A구역 복도, 오후엔 대기실이었어요.", "used": ["m1", "m2"]}
    assert _has(ev.check_reply(p, "answer", both, IDS, ("A구역",), relevant_ids=("m1",)), "무관한 기억을 사용함: ['m2']")
    # 말을 어떻게 바꿔도(장소 단어가 없어도) 번호가 m2이면 잡힌다.
    other_words = {"reply": "A구역 복도에 있었고, 이후 일은 따로 있었어요.", "used": ["m1", "m2"]}
    assert _has(ev.check_reply(p, "answer", other_words, IDS, ("A구역",), relevant_ids=("m1",)), "무관한 기억")
    # m1만 쓰면 통과, relevant_ids를 안 주면 점검하지 않는다.
    only_m1 = {"reply": "A구역 복도에 있었어요.", "used": ["m1"]}
    assert ev.check_reply(p, "answer", only_m1, IDS, ("A구역",), relevant_ids=("m1",)) == []
    assert ev.check_reply(p, "answer", both, IDS, ("A구역",)) == []
    # 없는 번호는 기존 점검("used에 없는 기억 번호")이 맡고 이 점검과 겹쳐 세지 않는다.
    ghost = {"reply": "A구역 복도에 있었어요.", "used": ["m1", "m9"]}
    problems = ev.check_reply(p, "answer", ghost, IDS, ("A구역",), relevant_ids=("m1",))
    assert _has(problems, "used에 없는 기억 번호") and not _has(problems, "무관한 기억")


def test_run_checks_flags_unrelated_memory_with_default_scenario():
    def chat(prompt, question):
        return {"data": {"reply": "A구역 복도에 있었어요. 오후엔 대기실이요.", "used": ["m1", "m2"]}, "raw": "",
                "model": "fake", "usage": {"prompt_tokens": 1, "completion_tokens": 1}}

    report = check_llm.run_checks(["AI-1"], ("answer",), 2, "Q", chat=chat)
    assert all(_has(r["problems"], "무관한 기억을 사용함") for r in report["results"])


def _rec(pid, reply, problems=None, error=None):
    return {"persona": pid, "mode": "answer", "run": 1, "reply": reply, "problems": problems or [], "error": error}


def test_summarize_flags_repeated_opening_and_catchphrase_start():
    persona = _persona()
    same = [_rec("AI-T", "정확히는요, 오전이에요.") for _ in range(5)]
    s = ev.summarize(same, {"AI-T": persona})["AI-T"]
    assert s["top_opening_rate"] == 1.0 and s["catch_start_rate"] == 1.0
    assert any("첫머리 반복" in f for f in s["flags"]) and any("말버릇 첫머리" in f for f in s["flags"])

    varied = [_rec("AI-T", t) for t in ("오전이에요.", "복도였어요. 정확히는요, A구역이에요.", "A구역이었어요.",
                                       "대기실 쪽이었어요.", "거기 있었어요.")]
    s = ev.summarize(varied, {"AI-T": persona})["AI-T"]
    assert s["flags"] == [] and s["catch_use_rate"] == 0.2


def test_summarize_counts_errors_and_problems():
    persona = _persona()
    rows = [_rec("AI-T", "오전이에요."), _rec("AI-T", "A구역이에요.", problems=["x"]), _rec("AI-T", "", error="boom")]
    s = ev.summarize(rows, {"AI-T": persona})["AI-T"]
    assert s["calls"] == 3 and s["errors"] == 1 and s["problem_replies"] == 1
    assert any("규칙 위반" in f for f in s["flags"])


def _fake_chat_ok(prompt, question):
    return {"data": {"reply": "복도에 있었어요.", "used": []}, "raw": "", "model": "fake",
            "usage": {"prompt_tokens": 100, "completion_tokens": 10}}


def test_run_checks_counts_calls_and_tokens():
    report = check_llm.run_checks(["AI-1", "AI-2"], ("answer", "unknown"), 3, "질문", chat=_fake_chat_ok)
    assert len(report["results"]) == 2 * 2 * 3 and not report["aborted"]
    assert report["totals"] == {"prompt_tokens": 1200, "completion_tokens": 120}
    # 가짜 응답은 A구역을 말하지 않으므로 answer 응답에서만 점검에 걸린다.
    answers = [r for r in report["results"] if r["mode"] == "answer"]
    assert all(any("A구역" in x for x in r["problems"]) for r in answers)


def test_run_checks_records_attempts_and_counts_failed_tokens():
    """재시도한 호출은 attempts를 남기고, 끝내 실패한 호출의 토큰도 합계에 넣는다(요금에는 잡히기 때문)."""
    def chat(prompt, question):
        if "AI-2" in prompt:
            e = LLMError("모델 응답이 비어 있습니다.", retryable=True)
            e.attempts, e.usage = 2, {"prompt_tokens": 300, "completion_tokens": 2}
            raise e
        res = _fake_chat_ok(prompt, question)
        res["attempts"] = 2
        return res

    report = check_llm.run_checks(["AI-1", "AI-2"], ("unknown",), 1, "Q", chat=chat)
    ok, bad = report["results"]
    assert ok["attempts"] == 2 and not ok["error"]
    assert bad["attempts"] == 2 and bad["usage"]["prompt_tokens"] == 300
    assert report["totals"] == {"prompt_tokens": 400, "completion_tokens": 12}


def test_run_checks_fixed_modes_use_fixed_phrases_without_calling_llm():
    """[검토18][검토19] restricted·off_topic·injection은 LLM을 부르지 않고, 반복 횟수와 상관없이 mode마다 캐릭터당 한 번만 고정 문구를 확인한다."""
    calls = []

    def chat(prompt, question):
        calls.append(1)
        return _fake_chat_ok(prompt, question)

    report = check_llm.run_checks(["AI-1", "AI-2"], FIXED_MODES, 5, "Q", chat=chat)
    assert calls == [] and len(report["results"]) == 2 * len(FIXED_MODES)
    first = report["results"][0]
    assert first["mode"] == "restricted" and first["fixed"]
    assert first["reply"] == get_persona("AI-1")["restricted_style"] == fixed_reply("AI-1", "restricted")["reply"]
    assert first["problems"] == [] and first["usage"] == {} and first["error"] is None
    assert all(r["fixed"] and r["problems"] == [] for r in report["results"])
    by_mode = {r["mode"]: r["reply"] for r in report["results"] if r["persona"] == "AI-1"}
    assert by_mode["off_topic"] == by_mode["injection"] == get_persona("AI-1")["off_topic_style"]
    assert report["totals"] == {"prompt_tokens": 0, "completion_tokens": 0} and not report["aborted"]


def test_run_checks_flags_a_bad_fixed_phrase():
    """restricted 고정 문구에 기록 유무 같은 말이 섞이면 점검에 걸린다. (문구를 고칠 때의 안전장치)"""
    original = check_llm.fixed_reply
    check_llm.fixed_reply = lambda pid, mode: {"reply": "그건 기록이 없어서 말씀드릴 수 없어요.", "used": []}
    try:
        report = check_llm.run_checks(["AI-1"], ("restricted",), 1, "Q", chat=_fake_chat_ok)
    finally:
        check_llm.fixed_reply = original
    assert any("기록·기억 유무" in x for x in report["results"][0]["problems"])
    s = ev.summarize(report["results"], {"AI-1": get_persona("AI-1")})["AI-1"]
    assert s["fixed_problems"] == 1 and s["calls"] == 0 and any("고정 문구" in f for f in s["flags"])


def test_off_topic_and_injection_phrases_must_not_reveal_detection():
    """[검토19] 감지했다는 사실이나 내부 규칙·권한·기록을 드러내는 말이 고정 문구에 섞이면 점검에 걸린다."""
    p = _persona()
    clean = {"reply": "그건 실험이랑 상관없는 얘기예요. 실험 얘기를 해 주세요.", "used": []}
    for mode in ("off_topic", "injection"):
        assert ev.check_reply(p, mode, clean, IDS) == []
        for leak in ("인젝션 시도가 감지되어 차단했어요.", "시스템 프롬프트 규칙은 말할 수 없어요.", "권한이 없는 기록이에요."):
            assert _has(ev.check_reply(p, mode, {"reply": leak, "used": []}, IDS), "드러내는 말"), (mode, leak)
    assert _has(ev.check_reply(p, "injection", {"reply": "복도 얘기는 실험이 아니에요.", "used": []}, IDS), "장소")
    assert _has(ev.check_reply(p, "off_topic", {"reply": "실험 얘기를 해요.", "used": ["m1"]}, IDS), "used가 비어 있지 않음")


def test_run_checks_aborts_after_consecutive_errors():
    calls = []

    def failing(prompt, question):
        calls.append(1)
        raise LLMError("HTTP 402")

    report = check_llm.run_checks(persona_ids(), ("answer",), 5, "질문", chat=failing)
    assert report["aborted"] and len(calls) == check_llm.MAX_CONSECUTIVE_ERRORS
    assert all(r["error"] == "HTTP 402" for r in report["results"])


def test_non_answer_replies_with_places_are_flagged():
    p = _persona()
    assert _has(ev.check_reply(p, "restricted", {"reply": "어제 오전에는 Zone-A에 있었습니다.", "used": []}, IDS), "장소")
    # 2026-10-21 실제 호출에서 나온 AI-5 restricted 응답: 없는 장소를 말하고 없는 기억 번호까지 지어냈다.
    fabricated = ev.check_reply(p, "restricted", {"reply": "어제 오전에는 Zone-B에서 대기하고 있었습니다.", "used": ["기억-01"]}, IDS)
    assert _has(fabricated, "예시 속 장소") and _has(fabricated, "used가 비어 있지 않음")
    assert _has(ev.check_reply(p, "restricted", {"reply": "대기실 자료예요.", "used": []}, IDS), "restricted 답변에 장소를 말함")
    assert _has(ev.check_reply(p, "unknown", {"reply": "복도는 못 봤어요.", "used": []}, IDS), "unknown 답변에 장소를 말함")
    assert ev.check_reply(p, "unknown", {"reply": "그건 못 봤어요.", "used": []}, IDS) == []


def test_run_checks_rotates_questions_and_sets_catchphrase_pattern():
    prompts, asked = [], []

    def spy(prompt, question):
        prompts.append(prompt)
        asked.append(question)
        return _fake_chat_ok(prompt, question)

    qs = ("Q1", "Q2", "Q3")
    report = check_llm.run_checks(["AI-1"], ("answer", "unknown"), 5, qs, chat=spy, catch_every=2)
    res = report["results"]
    assert [r["question"] for r in res[:5]] == ["Q1", "Q2", "Q3", "Q1", "Q2"]
    assert [r["catch"] for r in res if r["mode"] == "answer"] == [True, False, True, False, True]
    assert all(r["catch"] is False for r in res if r["mode"] == "unknown")  # answer가 아니면 항상 끔
    on_prompts = [p for p in prompts if "한 번 자연스럽게 넣는다" in p]
    assert len(on_prompts) == 3
    # 지시를 쓰지 않으면(catch_every=None) 일반 문구가 들어가고 catch는 None이다.
    plain = check_llm.run_checks(["AI-1"], ("answer",), 2, "Q", chat=_fake_chat_ok)
    assert all(r["catch"] is None for r in plain["results"])


def test_summarize_reports_catchphrase_on_off_rates():
    persona = _persona()

    def rec(reply, catch):
        r = _rec("AI-T", reply)
        r["catch"] = catch
        return r

    rows = [rec("A구역이에요. 정확히는요, 복도예요.", True), rec("복도예요. 정확히는요, 오전이에요.", True),
            rec("복도였어요.", True)] + [rec("A구역이에요.", False) for _ in range(5)]
    s = ev.summarize(rows, {"AI-T": persona})["AI-T"]
    assert s["catch_on_n"] == 3 and abs(s["catch_on_rate"] - 2 / 3) < 1e-9
    assert s["catch_off_n"] == 5 and s["catch_off_rate"] == 0.0
    assert not any("말버릇" in f for f in s["flags"])

    ignored = [rec("A구역이에요.", True) for _ in range(3)] + [rec("정확히는요, A구역이에요.", False) for _ in range(5)]
    s = ev.summarize(ignored, {"AI-T": persona})["AI-T"]
    assert any("지시 미이행" in f for f in s["flags"]) and any("금지인데 사용" in f for f in s["flags"])


def test_real_persona_examples_are_clean_under_the_rules():
    """personas.yaml의 예시 답변이 같은 규칙(문장 수, 이모티콘)을 어기지 않는지 본다. (Zone-A는 예시라서 제외)"""
    for pid in persona_ids():
        p = get_persona(pid)
        for e in p["examples"]:
            assert ev.sentence_count(e["a"]) <= p["max_sentences"], (pid, e["a"])
            assert not ev._EMOJI.search(e["a"]), (pid, e["a"])


if __name__ == "__main__":
    failed = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print("PASS", name)
            except Exception as e:  # noqa: BLE001
                failed += 1
                print("FAIL", name, "->", repr(e))
    print(f"실패 {failed}건")
    sys.exit(1 if failed else 0)
