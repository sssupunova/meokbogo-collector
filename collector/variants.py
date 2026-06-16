"""
상품명에서 변형속성을 뽑아낸다: 용량/중량 · 형태 · 입수(묶음) · 한정여부.

네이버 API는 이런 속성을 따로 안 주고 title 안에 섞어 보내므로
(예: "농심 신라면 컵 65g 6개입 한정기획"), 규칙 기반으로 긁어낸다.
완벽한 정규화가 아니라 1차 추출 — 정밀 정규화는 먹보고 앱 쪽에서.
"""

from __future__ import annotations

import re

# 용량/중량: 숫자 + 단위 (120g, 1.5L, 500ml, 1kg). 제목에서 처음 나오는 것을 취한다.
_VOLUME_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(kg|g|mg|ml|l)\b", re.IGNORECASE)

# 형태: (정규화 라벨, 탐지 패턴). 위에서부터 먼저 걸리는 하나만 취한다.
_FORM_PATTERNS = [
    ("컵", re.compile(r"컵")),
    ("캔", re.compile(r"캔")),
    ("병", re.compile(r"병|페트|PET", re.IGNORECASE)),
    ("박스", re.compile(r"박스|BOX|벌크", re.IGNORECASE)),
    ("팩", re.compile(r"팩|파우치")),
    ("봉지", re.compile(r"봉지|봉")),
    ("스틱", re.compile(r"스틱")),
]

# 입수(묶음): 5개입 / 20입 / x5 / 6개 / 30봉 …  위에서부터 먼저 걸리는 하나.
_PACK_PATTERNS = [
    re.compile(r"(\d+)\s*개입"),
    re.compile(r"(\d+)\s*입"),
    re.compile(r"[xX×*]\s*(\d+)\b"),
    re.compile(r"(\d+)\s*(?:개|봉|포|캔|병|팩|매|구)\b"),
]

# 한정/기획 여부: 걸리면 매칭된 키워드를 그대로 남긴다.
_LIMITED_RE = re.compile(r"한정판|한정|기획세트|기획|대용량|에디션|EDITION", re.IGNORECASE)


def _norm_unit(unit: str) -> str:
    u = unit.lower()
    return "L" if u == "l" else u  # 리터만 대문자, 나머지는 소문자(g/kg/ml/mg)


def parse_variants(name: str) -> dict:
    """상품명 → {'volume', 'form', 'pack', 'limited'} (없으면 빈 문자열)."""
    text = name or ""

    volume = ""
    m = _VOLUME_RE.search(text)
    if m:
        volume = f"{m.group(1).replace(',', '.')}{_norm_unit(m.group(2))}"

    form = ""
    for label, pat in _FORM_PATTERNS:
        if pat.search(text):
            form = label
            break

    pack = ""
    for pat in _PACK_PATTERNS:
        pm = pat.search(text)
        if pm:
            pack = f"{pm.group(1)}개입"
            break

    lm = _LIMITED_RE.search(text)
    limited = lm.group(0) if lm else ""

    return {"volume": volume, "form": form, "pack": pack, "limited": limited}
