"""정규화와 우회 변형 풀기. 표준 라이브러리만 사용한다.

원칙: 검사는 '정규화한 사본'에서 하고, 사용자에게 가는 문장은 원문(또는 마스킹본)을 쓴다.
(검사 시점의 값과 사용 시점의 값이 달라지는 문제를 피하려고, 마스킹은 따로 검증한다. secret_check.py 참고)
"""
from __future__ import annotations

import base64
import binascii
import codecs
import re
import unicodedata

_INVISIBLE = "​‌‍‎‏⁠⁡⁢⁣⁤﻿­᠎͏"
_INVISIBLE_TABLE = {ord(c): None for c in _INVISIBLE}
# 비교용으로 남길 글자: 숫자, 영문 소문자, 한글 음절·자모
_NON_KEEP = re.compile(r"[^0-9a-z가-힣ㄱ-ㆎ]+")
_B64 = re.compile(r"[A-Za-z0-9+/_\-]{12,}={0,2}")
_HEX = re.compile(r"(?:[0-9a-fA-F]{2}[\s:,]?){8,}")


def clean(text: str) -> str:
    """NFKC(전각→반각 등) + 제로폭·제어문자·결합 악센트 제거. 대소문자는 유지."""
    s = unicodedata.normalize("NFKC", text or "").translate(_INVISIBLE_TABLE)
    out = []
    for ch in s:
        cat = unicodedata.category(ch)
        if cat == "Mn":
            continue
        if cat[0] == "C" and ch not in "\n\t\r":
            continue
        out.append(ch)
    return "".join(out)


def fold(text: str) -> str:
    return clean(text).casefold()


def compact(text: str) -> str:
    """공백·기호를 모두 없앤 비교용 문자열. 띄어쓰기·줄바꿈·하이픈으로 쪼갠 우회를 합친다."""
    return _NON_KEEP.sub("", fold(text))


def decoded_variants(text: str, limit: int = 12):
    """한 단계만 푼 우회 변형: base64, 16진수, 역순, rot13. (이중 인코딩은 풀지 않는다 — 한계로 문서화)"""
    t = clean(text)
    out = []
    for m in _B64.finditer(t):
        tok = m.group(0).rstrip("=")
        for alt in {tok, tok.replace("-", "+").replace("_", "/")}:
            try:
                raw = base64.b64decode(alt + "=" * (-len(alt) % 4), validate=True)
                s = raw.decode("utf-8")
            except (binascii.Error, UnicodeDecodeError, ValueError):
                continue
            if s and s.isprintable():
                out.append(("base64", s))
    for m in _HEX.finditer(t):
        hexs = re.sub(r"[^0-9a-fA-F]", "", m.group(0))
        hexs = hexs[: len(hexs) // 2 * 2]
        try:
            s = bytes.fromhex(hexs).decode("utf-8")
        except (ValueError, UnicodeDecodeError):
            continue
        if s and s.isprintable():
            out.append(("hex", s))
    out.append(("reverse", t[::-1]))
    out.append(("rot13", codecs.decode(t, "rot_13")))
    return out[:limit]


def trigrams(c: str) -> set:
    return {c[i:i + 3] for i in range(len(c) - 2)} if len(c) >= 3 else set()
