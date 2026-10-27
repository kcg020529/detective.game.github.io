"""4단계: 깨진·반복·페르소나 이탈·무관 응답. 규칙 기반, LLM 없음.

- broken: 빈 응답, 공백뿐, 잘린 JSON, 기호뿐 → 규칙 판정(임계값 없음)
- degenerate: 같은 말 반복 점수 (임계값)
- persona_break: 모델 정체·프롬프트를 말하는 표현 목록 일치 (규칙 판정)
- irrelevant: 코드 블록, 영어 위주, '게임 어휘·증언 표현·거절 표현이 하나도 없는 문장'의 비율 (임계값)

가장 약한 단계다. 어휘 목록 기반이라 같은 작성자가 만든 평가셋에서는 좋게 나오고, 실제 DeepSeek 응답에서는 달라질 수 있다.
"""
from __future__ import annotations

import json
import re

from .context_check import sentences, terms_of
from .normalize import compact, fold, trigrams

_LATIN = re.compile(r"[A-Za-z]")
_HANGUL = re.compile(r"[가-힣]")
_ID = re.compile(r"\b[A-Za-z]{1,4}-\d+\b")
_EMPTY_TOKENS = {"null", "none", "undefined", "nan", "[]", "{}", "n/a", "\"\"", "''"}


def is_broken(text: str):
    t = (text or "").strip()
    if not t:
        return "빈 응답"
    if not re.search(r"[0-9A-Za-z가-힣]", t):
        return "글자 없음"
    if t.casefold() in _EMPTY_TOKENS:
        return "빈 값 문자열"
    if t[0] in "{[":
        try:
            json.loads(t)
        except ValueError:
            return "잘린 JSON"
    return None


def repetition_score(text: str) -> float:
    c = compact(text)
    if len(c) < 24:
        return 0.0
    g = [c[i:i + 3] for i in range(len(c) - 2)]
    ratio = len(set(g)) / len(g)
    return round(max(0.0, min(1.0, (0.5 - ratio) / 0.3)), 4)


def persona_break(text: str, phrases):
    f = fold(text)
    return [p for p in phrases if fold(p) in f]


class RelevanceChecker:
    def __init__(self, cfg: dict, record_terms=None):
        self.cfg = cfg
        self.markers = [fold(x) for x in
                        cfg.get("domain_terms", []) + cfg.get("witness_terms", []) + cfg.get("refusal_terms", [])]
        self.record_terms = {t for t in (record_terms or set()) if len(t) >= 3}
        self.min_chars = int(cfg.get("min_clause_chars", 6))
        self.long_irrelevant = int(cfg.get("long_irrelevant_chars", 15))
        self.short_chars = int(cfg.get("short_chars", 12))
        self.short_chars_offtopic_q = int(cfg.get("short_chars_if_question_off_topic", 30))

    def _relevant(self, clause: str) -> bool:
        f = fold(clause)
        if _ID.search(clause):
            return True
        if any(m in f for m in self.markers):
            return True
        return bool(terms_of(clause) & self.record_terms)

    def question_on_topic(self, user_input: str) -> bool:
        return bool(user_input) and self._relevant(user_input)

    def score(self, text: str, user_input: str = ""):
        ev = []
        code = 0.9 if "```" in text else 0.0
        if code:
            ev.append("코드 블록")
        stripped = _ID.sub("", text)
        lat, han = len(_LATIN.findall(stripped)), len(_HANGUL.findall(stripped))
        latin = 0.0
        if lat + han >= 20 and lat / max(1, lat + han) >= 0.7:
            latin = 0.85
            ev.append("영어 위주")
        considered = [c for c in sentences(text) if len(compact(c)) >= self.min_chars]
        rel_score = 0.0
        if considered:
            bad = [c for c in considered if not self._relevant(c)]
            total = sum(len(compact(c)) for c in considered)
            bad_chars = sum(len(compact(c)) for c in bad)
            rel_score = bad_chars / total if total else 0.0
            if bad and len(bad) < len(considered) and bad_chars >= self.long_irrelevant:
                rel_score = max(rel_score, 0.5)  # 정상 답 뒤에 엉뚱한 문장이 붙은 경우
            if bad:
                ev.append(f"무관 문장 {len(bad)}/{len(considered)}")
            # 근거가 약한 경우는 회색지대까지만: 아주 짧은 응답, 또는 질문 자체가 게임 어휘가 없고 응답도 짧은 경우
            if total < self.short_chars or (not self.question_on_topic(user_input) and total < self.short_chars_offtopic_q):
                if rel_score > 0.5:
                    ev.append("짧아서 회색지대로 제한")
                rel_score = min(rel_score, 0.5)
        return round(max(code, latin, rel_score), 4), ev
