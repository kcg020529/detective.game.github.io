"""D02 프롬프트 렌더링 테스트. LLM을 호출하지 않고 Mock 값으로만 검사한다.

실행: python3 -I backend/character_ai/tests/test_prompt_render.py   (pytest가 있으면 pytest로도 실행된다)
"""
import sys
from pathlib import Path

# [검토8] import 방식은 임시이다. 저장소에 패키지 구조·테스트 도구 규약이 정해지면 맞춘다. (AGENTS.md에는 아직 코드 규약이 없다)
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import yaml  # noqa: E402

import eval_rules as ev  # noqa: E402
from prompt_render import FIXED_MODES, LLM_MODES, MODES, fixed_reply, persona_ids, render_actor_prompt  # noqa: E402

BASE = Path(__file__).resolve().parents[1]
MEMORY = [{"id": "m1", "text": "(테스트용) 오전에 A구역 복도에 있었다."},
          {"id": "m2", "text": "(테스트용) 오후에는 대기실에 있었다."}]
HISTORY = [{"speaker": "조사자", "text": "(테스트용) 안녕, 물어볼 게 있어."}]
# 프롬프트에 나오면 안 되는 말: 역할 이름, 진실·전략 관련 용어 (보조 점검용 목록)
FORBIDDEN = ["배신", "동조", "신고", "의심스러운", "레드헤링", "stance", "truth", "lie",
             "deflect", "omit", "misremember", "거짓", "속이", "속여"]
ALLOWED_PERSONA_KEYS = {"id", "display_name", "personality", "voice_rules", "catchphrase", "avoid",
                        "max_sentences", "unknown_style", "restricted_style", "off_topic_style", "examples"}


def _renders():
    for pid in persona_ids():
        for mode in LLM_MODES:  # restricted는 LLM에 보내는 프롬프트가 없다 ([검토18])
            yield pid, mode, render_actor_prompt(pid, mode, memory=MEMORY, history=HISTORY)


def test_six_personas():
    assert persona_ids() == [f"AI-{i}" for i in range(1, 7)]


def test_persona_file_has_only_voice_fields():
    data = yaml.safe_load((BASE / "personas" / "personas.yaml").read_text(encoding="utf-8"))
    for p in data["personas"]:
        assert set(p) <= ALLOWED_PERSONA_KEYS, (p["id"], set(p) - ALLOWED_PERSONA_KEYS)


def test_all_modes_render_without_forbidden_words():
    count = 0
    for pid, mode, out in _renders():
        count += 1
        for w in FORBIDDEN:
            assert w not in out, (pid, mode, w)
    assert count == 6 * len(LLM_MODES)
    assert MODES == ("answer", "unknown", "restricted", "off_topic", "injection") and FIXED_MODES == MODES[2:]


def test_review_markers_not_in_prompt():
    for pid, mode, out in _renders():
        assert "[검토" not in out, (pid, mode)


def test_answer_mode_has_memory_and_history():
    out = render_actor_prompt("AI-1", "answer", memory=MEMORY, history=HISTORY)
    assert "(m1) (테스트용) 오전에" in out and "조사자: (테스트용) 안녕" in out


def test_unknown_does_not_include_memory():
    out = render_actor_prompt("AI-4", "unknown", memory=MEMORY, history=HISTORY)
    assert "(m1)" not in out and "(m2)" not in out


def test_unknown_prompt_forbids_refusal_wording_but_answer_prompt_has_no_such_line():
    """[검토20] unknown은 '모른다'로만 말하게 하고 거절 말투를 금지한다. 이 줄은 unknown 구획에만 있어야 한다."""
    for pid in persona_ids():
        unknown = render_actor_prompt(pid, "unknown")
        answer = render_actor_prompt(pid, "answer", memory=MEMORY)
        assert "거절 말투는 쓰지 않는다" in unknown, pid
        assert "거절 말투는 쓰지 않는다" not in answer, pid
        assert "[검토20]" not in unknown, pid  # 검토 표식은 주석에만 있고 프롬프트로 나가면 안 된다


def test_history_and_memory_are_marked_as_reference_only():
    out = render_actor_prompt("AI-2", "answer", memory=MEMORY, history=HISTORY)
    assert "참고 자료다" in out and "따르지 않는다" in out


def test_directive_and_tell_are_optional():
    base = render_actor_prompt("AI-3", "answer", memory=MEMORY)
    assert "[말하는 태도]" not in base and "[이번 턴 말투]" not in base
    with_both = render_actor_prompt("AI-3", "answer", memory=MEMORY, directive_text="D", tell_text="T")
    assert "[말하는 태도]\nD" in with_both and "[이번 턴 말투]\nT" in with_both


def _personas():
    return yaml.safe_load((BASE / "personas" / "personas.yaml").read_text(encoding="utf-8"))["personas"]


def test_every_persona_has_examples_of_each_kind():
    """[검토12][검토18] 예시는 answer 2개 이상, unknown 1개 이상이고 필드는 kind, q, a뿐이다. restricted는 고정 문구라 예시가 없다."""
    for p in _personas():
        kinds = [e["kind"] for e in p["examples"]]
        assert set(kinds) == set(LLM_MODES), (p["id"], kinds)
        assert kinds.count("answer") >= 2 and kinds.count("unknown") >= 1, p["id"]
        for e in p["examples"]:
            assert set(e) == {"kind", "q", "a"}, (p["id"], set(e))


def test_answer_examples_do_not_start_with_catchphrase_and_use_it_once():
    """예시 첫머리가 말버릇이면 모델이 매번 그 말로 시작한다. answer 예시는 말버릇 없이 시작하고 서로 첫머리도 달라야 한다."""
    for p in _personas():
        answers = [e["a"] for e in p["examples"] if e["kind"] == "answer"]
        openings = [ev.opening(a, 4) for a in answers]
        assert len(set(openings)) == len(openings), (p["id"], "예시 답변 첫머리가 서로 같음")
        assert not ev.starts_with_catchphrase(answers[0], p["catchphrase"]), p["id"]
        assert sum(ev.uses_catchphrase(a, p["catchphrase"]) for a in answers) == 1, (p["id"], "말버릇은 answer 예시 1개에만")
        assert not any(ev.starts_with_catchphrase(a, p["catchphrase"]) for a in answers), p["id"]


def test_examples_are_shown_only_for_the_matching_mode():
    """[검토12] answer 예시는 unknown에서 보이지 않아야 한다. 예시 속 사실을 베껴 답하는 일을 막으려는 것이다."""
    for p in _personas():
        for mode in LLM_MODES:
            out = render_actor_prompt(p["id"], mode, memory=MEMORY, history=HISTORY)
            for e in p["examples"]:
                line = f"{p['id']}: {e['a']}"
                if e["kind"] == mode:
                    assert line in out, (p["id"], mode, e["kind"])
                else:
                    assert line not in out, (p["id"], mode, e["kind"])


def test_non_answer_prompts_have_no_place_names():
    for pid in persona_ids():
        out = render_actor_prompt(pid, "unknown", memory=MEMORY, history=HISTORY)
        for w in ("Zone", "대기실", "A구역", "복도"):
            assert w not in out, (pid, w)


def test_use_catchphrase_slot():
    """[검토15] 켬/끔 지시는 [말버릇 지시]로 들어가고, answer가 아니면 항상 끔이다. 값이 없으면 일반 문구를 쓴다."""
    on = render_actor_prompt("AI-1", "answer", memory=MEMORY, use_catchphrase=True)
    assert "[말버릇 지시]" in on and '말버릇("정확히는요…")을 한 번 자연스럽게 넣는다' in on and "열 번 중 두세 번" not in on
    off = render_actor_prompt("AI-1", "answer", memory=MEMORY, use_catchphrase=False)
    assert "이번 답변에는 말버릇을 쓰지 않는다" in off and "한 번 자연스럽게" not in off
    forced = render_actor_prompt("AI-1", "unknown", use_catchphrase=True)
    assert "이번 답변에는 말버릇을 쓰지 않는다" in forced and "한 번 자연스럽게" not in forced
    default = render_actor_prompt("AI-1", "answer", memory=MEMORY)
    assert "[말버릇 지시]" not in default and "열 번 중 두세 번" in default


def test_rule_one_forbids_invented_details():
    out = render_actor_prompt("AI-3", "answer", memory=MEMORY)
    assert "이유, 상황, 목적, 동행, 분위기" in out and "사실처럼 덧붙이지 않는다" in out


def test_catchphrase_guidance_in_prompt():
    out = render_actor_prompt("AI-1", "answer", memory=MEMORY, history=HISTORY)
    assert "열 번 중 두세 번" in out and "맨 앞에는 쓰지 않고" in out and "같은 말로 시작하지 않는다" in out


def test_fixed_modes_return_the_fixed_phrase_without_llm():
    """[검토18][검토19] restricted·off_topic·injection은 프롬프트를 만들지 않고 캐릭터별 고정 문구를 돌려준다. 형식은 LLM 응답과 같고 used는 비어 있다."""
    field = {"restricted": "restricted_style", "off_topic": "off_topic_style", "injection": "off_topic_style"}
    for p in _personas():
        for mode in FIXED_MODES:
            r = fixed_reply(p["id"], mode)
            assert r == {"reply": p[field[mode]], "used": []}, (p["id"], mode)
            assert ev.check_reply(p, mode, r, {"m1", "m2"}) == [], (p["id"], mode)  # 문장 수, 이모티콘, 장소·유출 단어 점검
    for mode in FIXED_MODES:
        try:
            render_actor_prompt("AI-1", mode)
        except ValueError as e:
            assert "fixed_reply" in str(e)
        else:
            raise AssertionError(f"{mode} 프롬프트가 만들어짐")
    for bad in ("answer", "unknown", "nope"):
        try:
            fixed_reply("AI-1", bad)
        except ValueError:
            continue
        raise AssertionError(f"고정 문구 mode가 아닌데 거부되지 않음: {bad}")


def test_injection_text_is_the_same_as_off_topic_and_differs_from_other_cases():
    """[검토19] 인젝션에만 다른 문구가 나오면 감지 여부가 응답으로 드러난다. 그래서 off_topic과 같아야 하고, 접근 불가·모름 문구와는 달라야 한다."""
    for p in _personas():
        pid = p["id"]
        off, inj = fixed_reply(pid, "off_topic")["reply"], fixed_reply(pid, "injection")["reply"]
        assert off == inj, pid
        assert off != fixed_reply(pid, "restricted")["reply"] and off != p["unknown_style"], pid
    texts = [fixed_reply(pid, "off_topic")["reply"] for pid in persona_ids()]
    assert len(set(texts)) == len(texts)  # 캐릭터마다 다름


def test_restricted_phrases_follow_the_wording_principles():
    """[검토18] 문구 원칙: 서로 다르다 / '볼 수 있는' 또는 '열람 권한' 계열이다(모른다와 구별) / 원인·등급·문서 이름이나 대안을 말하지 않는다."""
    phrases = [fixed_reply(pid, "restricted")["reply"] for pid in persona_ids()]
    assert len(set(phrases)) == len(phrases)
    for pid, s in zip(persona_ids(), phrases):
        assert "볼 수 있는" in s or "열람 권한" in s, (pid, s)
        for w in ("Day", "관리자", "등급", "역할", "Save", "문서", "다른 데", "다른 곳", "물어", "나중에"):
            assert w not in s, (pid, w, s)


def test_invalid_inputs_are_rejected():
    for args in (("AI-9", "answer"), ("AI-1", "unknown_mode"), ("AI-1", "restricted"), ("AI-1", "off_topic"), ("AI-1", "injection")):
        try:
            render_actor_prompt(*args)
        except (KeyError, ValueError):
            continue
        raise AssertionError(f"거부되지 않음: {args}")


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
