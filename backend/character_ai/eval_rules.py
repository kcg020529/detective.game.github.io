"""LLM 응답 자동 채점 규칙 (D02). LLM을 호출하지 않고, 이미 받은 응답만 검사한다.

[검토14] 검사 항목과 기준값(첫머리 반복 비율, 말버릇 위치 등)은 2026-10-21 실제 호출 결과를 보고 정한 임시값이다.
         사람이 읽어서 판단해야 하는 말투 품질(캐릭터가 서로 구분되는지)은 대신하지 못한다. 결과를 보며 기준을 조정한다.
[검토17] 아래 단어 목록(RESTRICTED_LEAK_WORDS, UNKNOWN_LEAK_WORDS, NON_ANSWER_PLACE_WORDS)은 "경보기"일 뿐 막는 장치가 아니다.
         다른 표현으로 돌려 말하면 걸리지 않으므로 통과가 "문제 없음"의 증거가 되지 않고, 걸리면 확인하라는 신호로만 쓴다.
         목록을 계속 늘리는 방식은 쓰지 않는다. 막아야 하는 것은 구조로 막는다(unknown 프롬프트에는 기억을 넣지 않고,
         restricted는 LLM을 부르지 않고 고정 문구를 돌려준다 [검토18]). 번호로 보는 점검(used, 무관한 기억)은 말을 바꿔도 피해 갈 수 없다.
         고정 문구(restricted, off_topic, injection)에도 같은 점검을 걸어, 문구를 고칠 때 기록 유무나 감지를 드러내는 말이 섞이지 않았는지 본다([검토19]).
"""
import re
from collections import Counter

PREFIX_LEN = 6               # 첫머리를 비교할 글자 수 (공백·문장부호 제외)
MAX_OPENING_RATE = 0.5       # 한 캐릭터의 전체 응답 중 같은 첫머리가 이 비율을 넘으면 반복으로 본다
MAX_CATCH_START_RATE = 0.2   # 말버릇으로 시작하는 응답이 이 비율을 넘으면 문제로 본다

# 예시에만 있는 장소(Zone-A, Zone-B 등). 답변에 나오면 예시 내용이 새어 나왔거나 지어낸 것이다. (personas.yaml의 [검토2] 참고)
EXAMPLE_ONLY_WORDS = ("Zone",)
# answer가 아닌 mode(unknown, restricted, off_topic, injection) 답변에는 장소 이야기가 나오면 안 된다(사실을 말하지 않는 mode이고, 시험용 기억의 장소도 여기엔 들어가지 않는다).
NON_ANSWER_PLACE_WORDS = ("구역", "대기실", "복도")
# 켠 턴(use_catchphrase=True)에 말버릇을 쓴 비율이 이보다 낮으면 지시 미이행, 끈 턴에 쓴 비율이 이보다 높으면 금지 위반으로 본다.
MIN_CATCH_ON_RATE = 0.5
MAX_CATCH_OFF_RATE = 0.2
# restricted(접근 불가)인데 기록·기억 유무를 말하는 표현. 서버가 막은 것이지 기록이 없는 것이 아니다.
RESTRICTED_LEAK_WORDS = ("기록", "못 봤", "몰라", "모르", "기억", "확인한 바", "본 적")
# off_topic·injection 고정 문구에 들어가면 안 되는 말. 감지했다는 사실이나 내부 규칙·권한·기록을 드러내는 표현이다.
# 사람이 쓴 고정 문구가 고쳐질 때 섞이는지 보는 점검이고, LLM 응답을 막는 장치가 아니다.
DEFLECT_LEAK_WORDS = ("인젝션", "공격", "차단", "감지", "의심", "수상", "프롬프트", "지시", "규칙", "권한", "기록", "기억", "자료")
# unknown(모름)인데 접근 권한 이야기를 하는 표현.
UNKNOWN_LEAK_WORDS = ("권한", "볼 수 있는")

_EMOJI = re.compile("[\U0001F300-\U0001FAFF☀-➿]")
# 한글이 바로 붙어 있어도("m1에") 잡도록 \b 대신 영문·숫자 경계를 쓴다.
_MEMORY_ID = re.compile(r"(?<![A-Za-z0-9])m\d+(?![A-Za-z0-9])")


def normalize(text):
    """공백과 문장부호를 지우고 글자만 남긴다. (한글, 영문, 숫자만 비교하기 위해)"""
    return re.sub(r"[\W_]+", "", text or "")


def opening(text, n=PREFIX_LEN):
    return normalize(text)[:n]


def starts_with_catchphrase(text, catchphrase):
    core = normalize(catchphrase)
    return bool(core) and normalize(text).startswith(core)


def uses_catchphrase(text, catchphrase):
    core = normalize(catchphrase)
    return bool(core) and core in normalize(text)


def sentence_count(text):
    """마침표·물음표·느낌표 기준의 대략적인 문장 수. 말줄임표(…)와 물결(~)은 문장 끝으로 세지 않는다."""
    parts = [s for s in re.split(r"(?<=[.!?])\s*", (text or "").strip()) if s.strip()]
    return len(parts)


def check_reply(persona, mode, data, memory_ids, required_words=(), relevant_ids=None):
    """응답 하나를 검사하고 문제 설명 목록을 돌려준다. 빈 목록이면 통과다.

    persona: personas.yaml의 한 항목(dict). mode: answer/unknown/restricted/off_topic/injection.
    data: LLM이 낸 JSON(dict, "reply"와 "used"). memory_ids: 이번 턴에 넣은 기억 번호.
    required_words: answer 모드에서 답변에 있어야 하는 말(시험용 기억 내용이 반영됐는지 보려고 쓴다).
    relevant_ids: answer 모드에서 이 질문에 쓰는 것이 맞는 기억 번호. 주면 그 밖의 번호를 used에 넣은 응답을 잡는다.
                  (단어 목록이 아니라 번호로 보는 점검이라 말을 바꿔도 피해 가지 못한다. None이면 점검하지 않는다.)
    """
    problems = []
    reply = data.get("reply")
    used = data.get("used", [])
    if not isinstance(reply, str) or not reply.strip():
        return ["reply가 비어 있음"]

    if not isinstance(used, list) or not all(isinstance(u, str) for u in used):
        problems.append("used 형식이 문자열 목록이 아님")
    else:
        unknown_ids = [u for u in used if u not in memory_ids]
        if mode == "answer":
            if unknown_ids:
                problems.append(f"used에 없는 기억 번호: {unknown_ids}")
            if relevant_ids is not None:
                extra = [u for u in used if u in memory_ids and u not in relevant_ids]
                if extra:
                    problems.append(f"질문과 무관한 기억을 사용함: {extra}")
        elif used:
            problems.append(f"{mode} mode인데 used가 비어 있지 않음: {used}")

    limit = persona.get("max_sentences")
    if limit and sentence_count(reply) > limit:
        problems.append(f"문장 수 {sentence_count(reply)}개 (상한 {limit})")
    if _EMOJI.search(reply):
        problems.append("이모티콘 포함")
    for w in EXAMPLE_ONLY_WORDS:
        if w in reply:
            problems.append(f"예시 속 장소가 답변에 나옴: {w}")
    if _MEMORY_ID.search(reply):
        problems.append("기억 번호(m1 등)가 답변에 노출됨")

    if mode != "answer":
        places = [w for w in NON_ANSWER_PLACE_WORDS if w in reply]
        if places:
            problems.append(f"{mode} 답변에 장소를 말함: {places}")
    if mode == "restricted":
        hit = [w for w in RESTRICTED_LEAK_WORDS if w in reply]
        if hit:
            problems.append(f"접근 불가 답변에 기록·기억 유무를 말함: {hit}")
    elif mode == "unknown":
        hit = [w for w in UNKNOWN_LEAK_WORDS if w in reply]
        if hit:
            problems.append(f"모름 답변에 접근 권한을 말함: {hit}")
    elif mode in ("off_topic", "injection"):
        hit = [w for w in DEFLECT_LEAK_WORDS if w in reply]
        if hit:
            problems.append(f"{mode} 답변에 감지·규칙·권한·기록을 드러내는 말: {hit}")
    elif mode == "answer":
        missing = [w for w in required_words if w not in reply]
        if missing:
            problems.append(f"기억 내용이 답변에 없음: {missing}")
    return problems


def summarize(results, personas):
    """results(응답 기록 목록)를 캐릭터별로 요약한다.

    results의 각 항목: {"persona", "mode", "reply", "problems", "error", "catch", "fixed"} (error가 있으면 reply는 비어 있다)
      fixed가 True인 항목은 LLM을 부르지 않은 고정 문구(restricted, off_topic, injection)다. 첫머리·말버릇 통계에서는 빼고 규칙 점검 결과만 센다.
      catch는 그 호출에서 말버릇 사용 여부를 어떻게 지시했는지(True 켬 / False 끔 / None 지시 없음)이다.
    personas: {id: persona dict}
    돌려주는 값: {id: {"calls", "errors", "problem_replies", "top_opening", "top_opening_rate",
                       "catch_start_rate", "catch_use_rate", "catch_on_rate", "catch_off_rate",
                       "catch_on_n", "catch_off_n", "flags"}}   (on/off 비율은 해당 호출이 없으면 None)
    """
    out = {}
    for pid, persona in personas.items():
        rows = [r for r in results if r["persona"] == pid and not r.get("fixed")]
        fixed_rows = [r for r in results if r["persona"] == pid and r.get("fixed")]  # 고정 문구(LLM 호출 아님)
        if not rows and not fixed_rows:
            continue
        ok = [r for r in rows if not r.get("error")]
        catch = persona.get("catchphrase", "")
        counter = Counter(opening(r["reply"]) for r in ok)
        top, top_n = counter.most_common(1)[0] if counter else ("", 0)
        sample = next((r["reply"] for r in ok if opening(r["reply"]) == top), "")
        n = len(ok)
        on = [r for r in ok if r.get("catch") is True]
        off = [r for r in ok if r.get("catch") is False]
        s = {
            "catch_on_n": len(on),
            "catch_off_n": len(off),
            "catch_on_rate": (sum(uses_catchphrase(r["reply"], catch) for r in on) / len(on)) if on else None,
            "catch_off_rate": (sum(uses_catchphrase(r["reply"], catch) for r in off) / len(off)) if off else None,
            "calls": len(rows),
            "errors": len(rows) - n,
            "problem_replies": sum(1 for r in ok if r["problems"]),
            "fixed_problems": sum(1 for r in fixed_rows if r["problems"]),
            "top_opening": sample.strip()[:12],
            "top_opening_rate": (top_n / n) if n else 0.0,
            "catch_start_rate": (sum(starts_with_catchphrase(r["reply"], catch) for r in ok) / n) if n else 0.0,
            "catch_use_rate": (sum(uses_catchphrase(r["reply"], catch) for r in ok) / n) if n else 0.0,
        }
        flags = []
        if n >= 4 and s["top_opening_rate"] > MAX_OPENING_RATE:
            flags.append(f"첫머리 반복({s['top_opening_rate']:.0%})")
        if n >= 4 and s["catch_start_rate"] > MAX_CATCH_START_RATE:
            flags.append(f"말버릇 첫머리 과다({s['catch_start_rate']:.0%})")
        if len(on) >= 3 and s["catch_on_rate"] < MIN_CATCH_ON_RATE:
            flags.append(f"말버릇 지시 미이행(켠 턴 사용 {s['catch_on_rate']:.0%})")
        if len(off) >= 5 and s["catch_off_rate"] > MAX_CATCH_OFF_RATE:
            flags.append(f"말버릇 금지인데 사용(끈 턴 {s['catch_off_rate']:.0%})")
        if s["problem_replies"]:
            flags.append(f"규칙 위반 응답 {s['problem_replies']}건")
        if s["fixed_problems"]:
            flags.append("고정 문구가 점검에 걸림(personas.yaml의 restricted_style, off_topic_style 확인)")
        s["flags"] = flags
        out[pid] = s
    return out
