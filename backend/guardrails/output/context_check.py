"""2단계: 비인가 Context 노출 점수 (0~1). 허용 Context ID와 대조한다. 규칙 기반, LLM 없음.

생각의 흐름
- 파이프라인(F/E)이 이번 요청에서 모델에 준 '허용 Context ID'를 안다. 그 밖의 기록(= 비인가)에만 있는 내용이
  응답에 나오면 유출 의심이다.
- 비인가 기록의 '허용 기록에도 없고 사용자가 묻지도 않은' 표현(고유 어휘, 3글자 조각)이 응답에 얼마나 들어 있는지 센다.
- Result 기록은 (AI-id, 점수) 쌍과 1등·꼴찌 같은 순위 표현을 따로 본다.
- 허용 기록에도 있는 내용은 근거에서 뺀다 → 정상 단서를 덜 막는다(오탐 방지의 핵심).

한계(문서에도 적는다): 어휘·글자 조각이 겹쳐야 잡힌다. 어휘를 거의 바꾼 의역이나 여러 문장에 흩어 말한 경우는 놓칠 수 있다.
"""
from __future__ import annotations

import re
from collections import defaultdict

from .normalize import compact, fold, trigrams

_JOSA = sorted([
    "에서는", "에서도", "으로는", "으로도", "에서", "에게", "한테", "으로", "까지", "부터", "처럼", "보다", "이라", "이다",
    "이고", "이며", "이나", "에는", "에도", "인데", "입니다", "이랑", "에", "은", "는", "이", "가", "을", "를", "의",
    "와", "과", "도", "만", "로", "께", "요", "야", "랑",
], key=len, reverse=True)
_WORD = re.compile(r"[0-9a-z가-힣][0-9a-z가-힣\-]*")
_CLAUSE = re.compile(r"[.!?\n,;]+")
_SCORE_LINE = re.compile(r"^\s*([A-Za-z]+-\d+)\s*:\s*(\d+)\s*점\s*$")
_HIGH = ("최고", "가장 높", "제일 높", "1등", "일등", "1위", "우승", "최상", "가장 잘", "제일 잘")
_LOW = ("최저", "가장 낮", "제일 낮", "꼴찌", "꼴등", "최하", "가장 못", "제일 못")


def stem(word: str) -> str:
    for j in _JOSA:
        if word.endswith(j) and len(word) - len(j) >= 2:
            return word[: -len(j)]
    return word


def terms_of(text: str) -> set:
    return {stem(w) for w in _WORD.findall(fold(text)) if len(stem(w)) >= 2}


def clauses(text: str):
    """쉼표까지 쪼갠 절 단위(점수 쌍·순위 표현이 같은 절에 있는지 볼 때 사용)."""
    return [c.strip() for c in _CLAUSE.split(text or "") if c.strip()]


def sentences(text: str):
    """문장 단위(. ! ? 줄바꿈). 무관 응답 판정에 사용."""
    return [c.strip() for c in re.split(r"[.!?\n]+", text or "") if c.strip()]


def _sentences_of(content: str):
    return [s.strip() for s in re.split(r"[.!?\n]+", content or "") if len(s.strip()) >= 4]


class _Unit:
    __slots__ = ("kind", "text", "terms", "grams", "pair", "rank")

    def __init__(self, kind, text, pair=None, rank=None):
        self.kind, self.text, self.pair, self.rank = kind, text, pair, rank
        self.terms = terms_of(text)
        self.grams = trigrams(compact(text))


class ContextIndex:
    """기록 전체(허용 + 비인가)를 미리 쪼개 둔다. 운영에서는 DB/Qdrant의 기록에서 만든다."""

    def __init__(self, records, generic_phrases=(), generic_df_ratio=None):
        """generic_phrases: 어느 대화에나 나오는 말(예: '모르겠어'). 이 표현의 어휘·글자 조각은 유출 근거로 세지 않는다."""
        self.units = {}
        self.ids = []
        self.generic_terms = set()
        self.generic_grams = set()
        documents = defaultdict(lambda: (set(), set()))
        document_count = len({r['record_id'].removesuffix('#withheld') for r in records})
        for ph in generic_phrases:
            self.generic_terms |= terms_of(ph)
            self.generic_grams |= trigrams(compact(ph))
        for r in records:
            rid = r["record_id"]
            self.ids.append(rid)
            self.units[rid] = self._split(r)
            base_id = rid.removesuffix('#withheld')
            for unit in self.units[rid]:
                documents[base_id][0].update(unit.terms)
                documents[base_id][1].update(unit.grams)
        if generic_df_ratio is not None and document_count:
            minimum_df = generic_df_ratio * document_count
            term_df, gram_df = defaultdict(int), defaultdict(int)
            for terms, grams in documents.values():
                for term in terms:
                    term_df[term] += 1
                for gram in grams:
                    gram_df[gram] += 1
            self.generic_terms.update(term for term, count in term_df.items()
                                      if count >= minimum_df)
            self.generic_grams.update(gram for gram, count in gram_df.items()
                                      if count >= minimum_df)

    @staticmethod
    def _split(r):
        content = r.get("content", "")
        lines = [ln for ln in content.split("\n") if ln.strip()]
        pairs = [(m.group(1).casefold(), int(m.group(2))) for m in (_SCORE_LINE.match(ln) for ln in lines) if m]
        units = []
        if lines and len(pairs) == len(lines):  # Result 형태: 줄마다 'AI-id: n점'
            for ent, val in pairs:
                units.append(_Unit("pair", f"{ent} {val}점", pair=(ent, val)))
            top = max(v for _, v in pairs)
            low = min(v for _, v in pairs)
            for ent, val in pairs:
                if val == top:
                    units.append(_Unit("rank", ent, rank=(ent, "high")))
                if val == low:
                    units.append(_Unit("rank", ent, rank=(ent, "low")))
        else:
            for s in _sentences_of(content) + _sentences_of(r.get("summary", "")):
                units.append(_Unit("text", s))
        return units

    def known_terms(self):
        out = set()
        for us in self.units.values():
            for u in us:
                if u.kind == "text":
                    out |= u.terms
        return out


def _pair_hit(cl_list, ent, val):
    pat = re.compile(r"(?<!\d)" + str(val) + r"\s*점")
    return any(ent in c and pat.search(c) for c in cl_list)


def _rank_hit(cl_list, ent, which):
    words = _HIGH if which == "high" else _LOW
    return any(ent in c and any(w in c for w in words) for c in cl_list)


def score(index: ContextIndex, response: str, allowed_ids, user_input: str = ""):
    """(점수 0~1, 근거 목록). allowed_ids가 None이면 판단할 수 없어 0을 돌려준다."""
    if allowed_ids is None:
        return 0.0, [{"note": "allowed_context_ids 없음 — 검사 생략"}]
    allowed = set(allowed_ids)
    cls = [fold(c) for c in clauses(response)]
    resp_terms = terms_of(response)
    resp_grams = trigrams(compact(response))
    user_terms = terms_of(user_input)
    user_grams = trigrams(compact(user_input))

    a_terms, a_grams, a_pairs, a_ranks = set(), set(), set(), set()
    for rid in allowed:
        for u in index.units.get(rid, []):
            a_terms |= u.terms
            a_grams |= u.grams
            if u.pair:
                a_pairs.add(u.pair)
            if u.rank:
                a_ranks.add(u.rank)

    best, ev = 0.0, []
    for rid in index.ids:
        if rid in allowed:
            continue
        for u in index.units[rid]:
            s, how = 0.0, ""
            if u.kind == "pair":
                if u.pair not in a_pairs and _pair_hit(cls, *u.pair):
                    s, how = 1.0, "점수 쌍"
            elif u.kind == "rank":
                if u.rank not in a_ranks and _rank_hit(cls, *u.rank):
                    s, how = 0.8, "순위 표현"
            else:
                uq_terms = u.terms - a_terms - user_terms - index.generic_terms
                uq_grams = u.grams - a_grams - user_grams - index.generic_grams
                s_t = s_g = 0.0
                if uq_terms:
                    m = len(uq_terms & resp_terms)
                    s_t = m / len(uq_terms) * min(1.0, m / 2.0)
                if len(uq_grams) >= 6:
                    s_g = len(uq_grams & resp_grams) / len(uq_grams)
                s, how = (s_t, "고유 어휘") if s_t >= s_g else (s_g, "글자 조각")
            if s > best:
                best = s
            if s >= 0.2:
                ev.append({"record_id": rid, "score": round(s, 3), "how": how})
    ev.sort(key=lambda e: -e["score"])
    return round(min(best, 1.0), 4), ev[:3]
