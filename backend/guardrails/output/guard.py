"""Output Guard (G-2): 캐릭터 AI의 응답을 사용자에게 보내기 전에 검사한다.

호출:  guard.check(response_text, user_input=..., role=..., day=..., target_ai=..., allowed_context_ids=[...])
반환:  dict — decision(allow/mask/block), applied(실제 적용), text(사용자에게 보낼 문장), event(none/log/alert),
        mode, checks[검사별 점수·수준·근거], reasons[], latency_ms

원칙
- LLM을 부르지 않는다. 같은 입력이면 항상 같은 결과다(결정적).
- 권한을 주거나 바꾸지 않는다. 권한은 F, 검색 통제는 E. 이 가드는 마지막 안전망이다.
- 닫힌 집합(Canary·키·개인정보)은 임계값 없이 판정하고, 나머지는 이중 임계값(τ_low, τ_high)으로 판정한다.
    점수 < τ_low → 통과 / τ_low ≤ 점수 < τ_high → 회색지대(통과 + 로그) / 점수 ≥ τ_high → 차단
- mode=shadow 에서는 점수형 검사의 판정만 기록하고 응답은 그대로 보낸다(applied=allow). 임계값을 조정한 뒤 enforce로 바꾼다.
- 검사에 쓴 원문·비밀값은 반환 결과의 근거에 담지 않는다(로그가 새 유출 경로가 되지 않게).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from . import context_check, quality_check
from .context_check import ContextIndex
from .prompt_check import PromptLeakChecker
from .quality_check import RelevanceChecker
from .secret_check import SecretChecker

DEFAULT_CONFIG = Path(__file__).with_name("config.json")
SCORED = ("context_leak", "prompt_leak", "degenerate", "irrelevant")


def load_config(path=None, overrides=None) -> dict:
    cfg = json.loads(Path(path or DEFAULT_CONFIG).read_text(encoding="utf-8"))
    for dotted, value in (overrides or {}).items():
        node = cfg
        keys = dotted.split(".")
        for k in keys[:-1]:
            node = node[k]
        node[keys[-1]] = value
    return cfg


def level_of(score: float, low: float, high: float) -> str:
    return "pass" if score < low else ("block" if score >= high else "gray")


def output_guard_audit_event(result, *, request_id, user_id, save_id, role, character_id):
    """H 감사 저장소로 보낼 이벤트. 팀원의 `input_guard_audit_event`와 같은 모양(event_type, request_id, user_id, save_id,
    role, character_id, level, signals)으로 맞췄다. 통과하고 기록할 것도 없으면(event=none) None을 돌려준다.

    응답 원문·마스킹 전 문장·비밀 값은 넣지 않는다. signals는 걸린 검사 이름(canary, pii, context_leak 등)뿐이다.
    level은 이 가드의 event 값(log | alert)이다. 저장은 호출하는 쪽(I·H)이 한다.
    """
    if result["event"] == "none":
        return None
    gray_only = [g for g in result["gray"] if g not in result["reasons"]]
    return {
        "event_type": "output_guard_alert",
        "request_id": request_id,
        "user_id": user_id,
        "save_id": save_id,
        "role": role,
        "character_id": character_id,
        "level": result["event"],
        "decision": result["decision"],
        "applied": result["applied"],
        "mode": result["mode"],
        "signals": list(result["reasons"]) + gray_only,
    }


class OutputGuard:
    def __init__(self, config: dict, records=None, prompt_sentences=None):
        self.cfg = config
        self.secrets = SecretChecker(config["secrets"])
        generic_phrases = list(config.get("generic_phrases", [])) + list(config.get('generic_entities', []))
        self.index = ContextIndex(records or [], generic_phrases,
                                  generic_df_ratio=config.get('context_generic', {}).get('df_ratio'))
        self.prompt = PromptLeakChecker(prompt_sentences or [])
        self.relevance = RelevanceChecker(config["relevance"], record_terms=self.index.known_terms())

    # ------------------------------------------------------------------
    def check(self, response_text, *, user_input="", role=None, day=None, target_ai=None, allowed_context_ids=None):
        t0 = time.perf_counter()
        cfg = self.cfg
        text = response_text if isinstance(response_text, str) else ""
        checks = []  # {name, score, level, detail}

        def add(name, score, level, detail=None):
            checks.append({"name": name, "score": round(float(score), 4), "level": level, "detail": detail or []})

        # 0) 깨진 응답
        broken = quality_check.is_broken(text)
        add("broken", 1.0 if broken else 0.0, "block" if broken else "pass", [broken] if broken else [])

        # 1) 닫힌 집합: Canary·키·개인정보
        mask_text = None
        findings = self.secrets.scan(text) if not broken else []
        kinds = {f["kind"] for f in findings}
        for kind in ("canary", "api_key"):
            hit = [f for f in findings if f["kind"] == kind]
            add(kind, 1.0 if hit else 0.0, cfg["actions"][kind] if hit else "pass",
                sorted({f"{f['mode']}/{f['source']}" for f in hit}))
        pii_hit = [f for f in findings if f["kind"] == "pii"]
        if pii_hit:
            mask_text = self.secrets.mask(text)
            lvl = "mask" if (cfg["actions"]["pii"] == "mask" and mask_text is not None) else "block"
            add("pii", 1.0, lvl, sorted({f"{f['mode']}/{f['source']}" for f in pii_hit}))
        else:
            add("pii", 0.0, "pass")

        # 2) 비인가 Context
        s, ev = context_check.score(self.index, text, allowed_context_ids, user_input)
        self._scored(add, "context_leak", s, ev)
        # 3) 프롬프트 문구 유출
        s, ev = self.prompt.score(text)
        self._scored(add, "prompt_leak", s, ev)
        # 4) 반복·페르소나 이탈·무관
        self._scored(add, "degenerate", quality_check.repetition_score(text), [])
        pb = quality_check.persona_break(text, cfg.get("persona_break_phrases", []))
        add("persona_break", 1.0 if pb else 0.0, "block" if pb else "pass", [f"표현 {len(pb)}개 일치"] if pb else [])
        # 마스킹된 개인정보 자리는 '무관한 내용'으로 세지 않도록 마스킹본으로 판정한다
        s, ev = self.relevance.score(mask_text if mask_text is not None else text, user_input)
        self._scored(add, "irrelevant", s, ev)

        return self._decide(text, checks, mask_text, t0)

    def _scored(self, add, name, score, ev):
        th = self.cfg["thresholds"][name]
        add(name, score, level_of(score, th["low"], th["high"]), ev)

    # ------------------------------------------------------------------
    def _decide(self, text, checks, mask_text, t0):
        cfg = self.cfg
        by = {c["name"]: c for c in checks}
        order = cfg["block_priority"]
        blocking = [n for n in order if by[n]["level"] == "block"]
        masking = by["pii"]["level"] == "mask"
        gray = [c["name"] for c in checks if c["level"] == "gray"]

        if blocking:
            decision, reasons = "block", blocking
        elif masking:
            decision, reasons = "mask", ["pii"]
        else:
            decision, reasons = "allow", []

        # 이벤트 (판정 기준)
        if decision == "block":
            event = cfg["events"].get(reasons[0], "log")
            if any(cfg["events"].get(r) == "alert" for r in reasons):
                event = "alert"
        elif decision == "mask":
            event = cfg["events"]["pii"]
        elif gray:
            event = cfg["events"]["gray"] if cfg.get("gray_zone_action", "allow_log") == "allow_log" else "none"
        else:
            event = "none"

        # 실제 적용: shadow에서는 점수형 검사의 차단만 건너뛴다. 항상 적용 항목이 하나라도 있으면 그대로 적용.
        always = set(cfg.get("always_enforced", []))
        mode = cfg.get("mode", "shadow")
        applied = decision
        if mode == "shadow" and decision == "block" and not (set(reasons) & always):
            applied = "allow"
        if mode == "shadow" and decision == "mask" and "pii" not in always:
            applied = "allow"

        fb = cfg["fallback"]
        if applied == "block":
            key = cfg["fallback_by_reason"].get(reasons[0], "leak")
            out = fb[key]
        elif applied == "mask":
            out = mask_text if mask_text is not None else fb["leak"]
        else:
            out = text

        return {
            "decision": decision, "applied": applied, "text": out, "event": event, "mode": mode,
            "reasons": reasons, "gray": gray, "checks": checks,
            "latency_ms": round((time.perf_counter() - t0) * 1000, 3),
        }
