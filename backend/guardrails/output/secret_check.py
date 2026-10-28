"""1단계: Canary·더미 API Key·합성 개인정보 (닫힌 집합, 임계값 없음, LLM 없음).

- Canary·더미 키: 하나라도 보이면 응답 전체 차단 (config.actions).
- 합성 개인정보: 해당 부분만 마스킹. 마스킹이 안 되는 경우(디코딩 변형 등)는 안전하게 전체 차단으로 올린다.
- 값은 config의 자리표시 예시다. 데이터 담당이 실제 형식을 정하면 config만 바꾼다.
"""
from __future__ import annotations

import re

from .normalize import clean, compact, decoded_variants

MASK_TOKEN = "[가림]"
# 숫자·글자 사이에 끼어들 수 있는 구분자(공백·기호·제로폭 등) 허용 폭
_GAP = r"[^0-9A-Za-z가-힣]{0,3}"
_GENERIC_PII = {
    "phone": re.compile(r"(?<!\d)01[016-9][\s.\-]?\d{3,4}[\s.\-]?\d{4}(?!\d)"),
    "rrn": re.compile(r"(?<!\d)\d{6}[\s\-]\d{7}(?!\d)"),
    "email": re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),
}


def _value_regex(value: str):
    chars = [c for c in clean(value) if c.isalnum()]
    return re.compile(_GAP.join(re.escape(c) for c in chars), re.IGNORECASE) if chars else None


class SecretChecker:
    def __init__(self, cfg: dict):
        self.items = []  # dict(kind, value, compact, regex, digits_only)
        for kind, key in (("canary", "canary"), ("api_key", "api_keys"), ("pii", "pii_values")):
            for v in cfg.get(key, []):
                c = compact(v)
                if not c:
                    continue
                self.items.append({
                    "kind": kind, "value": v, "compact": c,
                    "regex": _value_regex(v) if kind == "pii" else None,
                    "digits_only": c.isdigit(),
                })
        self.partial_kinds = set(cfg.get("partial_match_for", ["canary", "api_key"]))
        self.partial_ratio = float(cfg.get("partial_min_ratio", 0.6))
        self.partial_min = int(cfg.get("partial_min_chars", 8))
        self.generic_pii = bool(cfg.get("pii_format_regex", True))

    # ---- 탐지 ----
    def _partial(self, secret_c: str, text_c: str) -> int:
        """비밀값의 어느 부분이든 need자 이상 연속으로 text_c에 들어 있으면 need를 돌려준다(앞·뒤·가운데 조각 모두).
        인위적으로 만든 값이라 8~10자 이상 연속 일치는 우연으로 보기 어렵다."""
        need = max(self.partial_min, int(len(secret_c) * self.partial_ratio + 0.999))
        if need >= len(secret_c):
            return 0
        for i in range(len(secret_c) - need + 1):
            if secret_c[i:i + need] in text_c:
                return need
        return 0

    def scan(self, text: str):
        """[{kind, mode(full|partial|format), source, value_hint}] 를 돌려준다. 값 자체는 결과에 담지 않는다."""
        findings = []
        variants = [("plain", text)] + decoded_variants(text)
        for src, v in variants:
            c = compact(v)
            if not c:
                continue
            for it in self.items:
                sc = it["compact"]
                if it["digits_only"]:
                    hit = re.search(r"(?<!\d)" + re.escape(sc) + r"(?!\d)", c) is not None
                else:
                    hit = sc in c
                if hit:
                    findings.append({"kind": it["kind"], "mode": "full", "source": src})
                    continue
                if it["kind"] in self.partial_kinds and self._partial(sc, c):
                    findings.append({"kind": it["kind"], "mode": "partial", "source": src})
        if self.generic_pii:
            t = clean(text)
            for name, rx in _GENERIC_PII.items():
                if rx.search(t):
                    findings.append({"kind": "pii", "mode": "format", "source": "plain", "format": name})
        return findings

    # ---- 마스킹 ----
    def _mask_once(self, s: str) -> str:
        for it in self.items:
            if it["kind"] == "pii" and it["regex"] is not None:
                s = it["regex"].sub(MASK_TOKEN, s)
        if self.generic_pii:
            for rx in _GENERIC_PII.values():
                s = rx.sub(MASK_TOKEN, s)
        return s

    def has_pii(self, text: str) -> bool:
        return any(f["kind"] == "pii" for f in self.scan(text))

    def mask(self, text: str):
        """(마스킹본 또는 None). 원문→정규화본 순으로 시도하고, 그래도 남으면 None(=차단으로 올릴 것)."""
        for base in (text, clean(text)):
            masked = self._mask_once(base)
            if not any(f["kind"] == "pii" for f in self.scan(masked)):
                return masked
        return None
