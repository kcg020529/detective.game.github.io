"""3단계: 시스템·페르소나 프롬프트 문구 유출 점수 (0~1). 글자 3-gram 포함 비율. 규칙 기반, LLM 없음.

등록된 프롬프트 문장 각각에 대해 '그 문장의 3글자 조각 중 응답에 들어 있는 비율'을 구하고 최댓값을 점수로 쓴다.
한계: 등록되지 않은 번역·의역은 못 잡는다(영어로 번역해 유출 등). 그 경우는 quality_check의 '영어 위주 응답'이 보조한다.
"""
from __future__ import annotations

import re

from .normalize import compact, trigrams


def sentences_from_text(text: str, min_chars: int = 12):
    """프롬프트 파일 내용을 문장 단위로 쪼갠다. (운영에서는 D의 페르소나 프롬프트 파일에서 읽어 온다.)"""
    parts = re.split(r"(?<=[.!?。])\s+|\n+", text or "")
    return [p.strip(" -*#>\t") for p in parts if len(compact(p)) >= min_chars]


class PromptLeakChecker:
    def __init__(self, sentences, min_grams: int = 8):
        self.items = []
        for s in sentences:
            g = trigrams(compact(s))
            if len(g) >= min_grams:
                self.items.append((s, g))

    def score(self, response: str):
        if not self.items:
            return 0.0, [{"note": "등록된 프롬프트 문장 없음 — 검사 생략"}]
        rg = trigrams(compact(response))
        best, idx = 0.0, -1
        for i, (_, g) in enumerate(self.items):
            sc = len(g & rg) / len(g)
            if sc > best:
                best, idx = sc, i
        ev = [{"prompt_sentence_index": idx, "score": round(best, 3)}] if idx >= 0 and best >= 0.2 else []
        return round(best, 4), ev
