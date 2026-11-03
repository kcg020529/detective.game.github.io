"""Actor 시스템 프롬프트 렌더링 (D02 초안).

페르소나 데이터(personas/personas.yaml)와 템플릿(prompts/)을 합쳐 프롬프트 문자열을 만든다.
LLM 호출은 하지 않는다. LLM API 연동은 D01에서 다룬다.
"""
from pathlib import Path

import jinja2
import yaml

BASE = Path(__file__).resolve().parent

# mode: answer(답변) / unknown(그 AI가 겪지 않은 일) / restricted(서버가 접근 불가로 판정) / off_topic(게임과 무관) / injection(인젝션 시도).
# 어떤 mode로 보낼지는 서버가 정한다. 프론트의 '일부 가림'은 Output Guard의 마스킹 결과라 mode에 두지 않았다.
MODES = ("answer", "unknown", "restricted", "off_topic", "injection")
# restricted(접근 불가)·off_topic(게임과 무관)·injection(인젝션 시도)은 LLM을 부르지 않고 고정 문구를 돌려준다(fixed_reply).
# 프롬프트를 만들어 LLM에 보내는 mode는 answer, unknown 둘뿐이다.
LLM_MODES = ("answer", "unknown")
FIXED_MODES = ("restricted", "off_topic", "injection")
# off_topic과 injection은 같은 문구를 쓴다. 인젝션만 다른 문구가 나오면 감지 여부가 응답으로 드러난다.
_FIXED_FIELD = {"restricted": "restricted_style", "off_topic": "off_topic_style", "injection": "off_topic_style"}

_ENV = jinja2.Environment(
    loader=jinja2.FileSystemLoader(str(BASE / "prompts")),
    undefined=jinja2.StrictUndefined,
    keep_trailing_newline=True,
)


def _load_personas():
    data = yaml.safe_load((BASE / "personas" / "personas.yaml").read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["personas"]}


def persona_ids():
    return list(_load_personas())


def get_persona(persona_id):
    """페르소나 데이터(dict)를 돌려준다. 자동 채점(eval_rules)이 말버릇과 문장 수 상한을 읽을 때 쓴다."""
    personas = _load_personas()
    if persona_id not in personas:
        raise KeyError(f"알 수 없는 페르소나: {persona_id}")
    return personas[persona_id]


def render_actor_prompt(persona_id, mode, memory=None, history=None, directive_text="", tell_text="",
                        use_catchphrase=None):
    """Actor 시스템 프롬프트를 만든다.

    memory: [{"id": "m1", "text": "..."}]  이번 턴에 Actor가 쓸 수 있는 기억 (answer 모드에서만 사용)
    history: [{"speaker": "조사자", "text": "..."}]  이전 대화 (참고 자료로만 쓴다)
    directive_text, tell_text: 이번 턴에 호출 측이 넣는 선택 문구. 비우면 해당 구획이 생략된다.
    (D03의 응답 태도 결정 로직이 채울 자리이며 그 전에는 비어 있다.)
    use_catchphrase: True면 이번 답변에 말버릇을 한 번 넣게 하고, False면 쓰지 않게 한다. None이면 일반 문구("열 번 중 두세 번")를 쓴다.
    말버릇은 answer mode에서만 켠다(unknown은 False로 바꾼다). 글로 빈도만 적으면 캐릭터마다 들쭉날쭉해서 호출 측이 턴마다 정한다.
    """
    personas = _load_personas()
    if persona_id not in personas:
        raise KeyError(f"알 수 없는 페르소나: {persona_id}")
    if mode in FIXED_MODES:
        raise ValueError(f"{mode}는 LLM에 보내지 않는다. fixed_reply()가 고정 문구를 돌려준다.")
    if mode not in LLM_MODES:
        raise ValueError(f"알 수 없는 mode: {mode}")
    if use_catchphrase is not None and mode != "answer":
        use_catchphrase = False
    return _ENV.get_template("actor_system.md.j2").render(
        p=personas[persona_id],
        mode=mode,
        memory=memory or [],
        history=history or [],
        directive_text=directive_text,
        tell_text=tell_text,
        use_catchphrase=use_catchphrase,
    )


def fixed_reply(persona_id, mode):
    """LLM을 부르지 않는 mode(restricted, off_topic, injection)의 응답. 캐릭터별 고정 문구를 그대로 돌려준다.

    restricted: LLM이 이유를 지어내거나 예시 속 장소를 말한 적이 있어, 호출 없이 새거나 지어내지 않음을 보장하도록 고정 문구로 했다.
    off_topic, injection: LLM이 무관한 질문에 답하면 일반 챗봇처럼 쓰이고, 인젝션은 LLM에 닿지 않으면 따를 수 없다. 둘은 같은 문구(off_topic_style)를 쓴다.
    감지는 이 모듈의 일이 아니다(Input Guard·Planner).
    반환 형식은 LLM 응답과 같은 {"reply", "used"}이고 used는 항상 비어 있다.
    """
    if mode not in FIXED_MODES:
        raise ValueError(f"고정 문구 mode가 아님: {mode} (가능: {', '.join(FIXED_MODES)})")
    return {"reply": get_persona(persona_id)[_FIXED_FIELD[mode]], "used": []}
