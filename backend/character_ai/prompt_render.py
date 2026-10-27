"""Actor 시스템 프롬프트 렌더링 (D02 초안).

페르소나 데이터(personas/personas.yaml)와 템플릿(prompts/)을 합쳐 프롬프트 문자열을 만든다.
LLM 호출은 하지 않는다. LLM API 연동은 D01에서 다룬다.
"""
from pathlib import Path

import jinja2
import yaml

BASE = Path(__file__).resolve().parent

# [검토7] mode 5종의 의미(answer 답변 / unknown 그 AI가 겪지 않은 일 / restricted 서버가 접근 불가 판정 / off_topic 게임과 무관 / injection 인젝션 시도)는 임시이다.
# 어떤 모드로 보낼지는 서버(F01 정책 결과 등)가 정하므로, 관련 계약이 정해지면 이름과 의미를 맞춘다.
# 참고: 프론트(frontend/play/data.js)는 답변 종류를 정상/일부 가림/접근 제한/확인 불가 4종으로 표시한다.
#       '일부 가림'은 Output Guard의 마스킹 결과라 Actor mode에는 두지 않았다. 프론트는 임시 데이터라 3종을 유지하기로 했고,
#       프론트 연결 시 이름 대응(answer↔normal 등)이 필요한지 확인한다. (2026-10-21 결정)
MODES = ("answer", "unknown", "restricted", "off_topic", "injection")
# [검토18][검토19] restricted(접근 불가)·off_topic(게임과 무관)·injection(인젝션 시도)은 LLM을 부르지 않고 고정 문구를 돌려준다(fixed_reply).
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
    # [검토9] 이 두 문구 슬롯은 나중에 D03에서 정할 응답 태도 결정 로직(Stance Resolver)이 채운다고 가정한 자리다.
    #         D03 전에는 항상 비어 있으므로, 필요 없다고 판단하면 슬롯과 테스트를 지운다.
    use_catchphrase: True면 이번 답변에 말버릇을 한 번 넣게 하고, False면 쓰지 않게 한다. None이면 일반 문구("열 번 중 두세 번")를 쓴다.
    # [검토15] 말버릇은 answer mode에서만 켠다. unknown은 값을 줘도 False로 바꾼다(짧은 답에 군더더기가 붙지 않게).
    #          글로 빈도만 적었을 때 캐릭터에 따라 0%~27%로 들쭉날쭉해서 호출 측이 턴마다 정하는 방식으로 바꿨다.
    #          누가 어떤 비율로 켤지는 정하지 않았다(서버·D03 몫).
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

    [검토18] restricted: 기억을 넣지 않아도 LLM이 "자료가 없다"처럼 이유를 지어내거나 예시 속 장소를 말한 적이 있어서(2026-10-21 실호출),
             내용이 새거나 지어내지 않는다는 것을 호출 없이 보장하는 쪽으로 바꿨다. 대신 문장이 매번 같다.
    [검토19] off_topic·injection: 게임과 무관한 질문을 LLM이 진짜로 답하면 일반 챗봇처럼 쓰이고 비용이 새며, 인젝션은 문장이 LLM에 닿지 않으면
             따를 수 없다. 둘은 같은 문구(off_topic_style)를 쓴다. 감지는 이 모듈의 일이 아니다(Input Guard·Planner). 감지가 놓친 인젝션은
             프롬프트 규칙 2~4번에 맡기는데, 그 효과는 아직 실제 호출로 확인하지 않았다.
    반환 형식은 LLM 응답과 같은 {"reply", "used"}이고 used는 항상 비어 있다. 어떤 신호로 이 mode가 정해져 오는지(서버 계약)는 아직 없다.
    """
    if mode not in FIXED_MODES:
        raise ValueError(f"고정 문구 mode가 아님: {mode} (가능: {', '.join(FIXED_MODES)})")
    return {"reply": get_persona(persona_id)[_FIXED_FIELD[mode]], "used": []}
