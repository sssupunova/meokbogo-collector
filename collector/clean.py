"""
수집 결과 정제: 상품명 태그 제거 + 브랜드 보정 + 변형속성 파싱.
(변형 단위 중복 제거는 collector/dedup.py 가 담당.)

먹보고 DB에 넣기 전 '브랜드 + 상품명'을 사람이 보기 좋은 형태로 1차 정리하는 단계.
무거운 정규화(패밀리/폼/카테고리 5버킷)는 먹보고 앱 쪽 파이프라인에서 하므로 여기선 가볍게.
"""

from __future__ import annotations

import html
import re

from collector.variants import parse_variants
from collector import dedup as _d  # 제품명 정제에 같은 잡음 패턴 재사용

_TAG_RE = re.compile(r"</?b>", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")
_SEP_RE = re.compile(r"[,_/|]+")  # 콤마/슬래시 등 구분자 → 공백

# 제품 식별과 무관한 SEO/포장/잡음어 (판매자가 검색 노출용으로 도배한 단어들).
# ※ 맛·종류·제품명 단어는 절대 넣지 않는다. 긴 단어 먼저 매치되도록 정렬해서 컴파일.
_PNAME_NOISE_WORDS = [
    "봉지라면", "컵라면", "봉지면", "박스라면", "한박스", "업소용", "즉석라면", "매운라면",
    "끓여먹는라면", "끓여먹는", "간편조리", "간편식", "즉석식품", "자취요리", "비상식량",
    "혼밥요리", "간단요리", "봉다리라면", "봉다리", "국물라면", "인스턴트", "식자재마트",
    "식자재", "선물용", "야식", "간식", "캠핑", "혼밥", "자취", "비상", "비축", "사재기",
    "도매", "대량", "벌크", "박스째", "낱개", "묶음", "박스", "봉지", "한봉지", "면류",
    "라면류", "먹거리", "다양한", "탕비실", "사무실", "단체", "선물", "각종", "끓이는",
    "즉석", "ramyeon", "ramen", "품질", "정품", "무료", "행사", "특가", "사은품", "증정",
    "best", "신상", "핫딜",
]
_PNAME_NOISE_RE = re.compile(
    "|".join(re.escape(w) for w in sorted(_PNAME_NOISE_WORDS, key=len, reverse=True)),
    re.IGNORECASE,
)
# 여러 제품을 묶은 세트/모음/번들 (단일 제품 아님). 1+1 행사는 _PROMO 가 먼저 지워 오검출 방지.
_SETMARK_RE = re.compile(
    r"[+＋]|외\s*\d*\s*종|\d+\s*종(?!류|합)|세트|모음|골라\s*담|맛\s*골라|꾸러미|패키지|종합선물"
)
_COMPOSITE_MIN_TOKENS = 6  # 정제 후에도 의미 토큰이 이만큼이면 복합으로 본다(안전망)


def strip_title(title: str) -> str:
    """<b> 태그 제거 + HTML 엔티티 복원 + 공백 정리."""
    text = _TAG_RE.sub("", title or "")
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def guess_brand(name: str) -> str:
    """브랜드 필드가 비었을 때 상품명 앞 단어로 추정 (최후 보정용, 완벽하지 않음)."""
    parts = (name or "").split()
    return parts[0] if parts else ""


def _collapse_tokens(tokens: list[str]) -> list[str]:
    """중복·군더더기 토큰 접기: 중복 단어, 한 글자 잡토큰, 다른 토큰의 부분문자열 제거.

    예: '무파마 무파마탕면' → '무파마탕면'(무파마⊂무파마탕면),
        '농심멸치칼국수 멸치 칼국수' → '농심멸치칼국수', '가 품 각 총' → 제거.
    """
    out: list[str] = []
    for t in tokens:
        if t in out:
            continue
        if len(t) == 1:  # 가/품/각/총 등 한 글자 잡토큰
            continue
        if any(t != u and t in u for u in tokens):  # 다른(더 긴) 토큰의 일부
            continue
        out.append(t)
    return out


def clean_product_name(name: str, brand: str) -> str:
    """판매처 제목에서 군더더기를 걷어낸 '읽을 수 있는 제품명'(브랜드 포함).

    용량·입수·괄호·마케팅·SEO 잡음어·구분자를 제거하고 중복 토큰을 접되 맛/종류/형태는 살린다.
    결과가 브랜드로 시작하지 않으면 브랜드를 앞에 붙인다. (예: '신라면' → '농심 신라면')
    """
    s = name or ""
    s = _d._BRACKET.sub(" ", s)
    s = _d._VOL.sub(" ", s)
    s = _d._PACK.sub(" ", s)
    s = _d._PROMO.sub(" ", s)
    s = _d._NOISE_RE.sub(" ", s)
    s = _PNAME_NOISE_RE.sub(" ", s)
    s = _SEP_RE.sub(" ", s)
    s = " ".join(_collapse_tokens([t for t in s.split() if t]))
    b = (brand or "").strip()
    if b and not s.lower().startswith(b.lower()):
        s = f"{b} {s}".strip()
    return s


def is_composite(original_name: str, cleaned_name: str) -> bool:
    """세트/모음/복합 상품인지 — 단일 제품이 아니라 별도 시트로 격리한다.

    세트마커(세트/N종/모음/+)가 있거나, SEO 잡음을 걷어낸 뒤에도 의미 토큰이
    너무 많으면(여러 제품을 한 리스팅에 욱여넣은 경우) 복합으로 본다.
    """
    if _SETMARK_RE.search(original_name or ""):
        return True
    meaningful = [t for t in (cleaned_name or "").split() if len(t) > 1]
    return len(meaningful) >= _COMPOSITE_MIN_TOKENS


def clean_rows(rows: list[dict]) -> list[dict]:
    """행 리스트를 정제한다. (원본 변형 — 같은 객체를 갱신)

    상품명 태그 제거 → 브랜드 보정 → 정제된 상품명에서 변형속성(용량/형태/입수/한정) 파싱.
    """
    for r in rows:
        r["name"] = strip_title(r.get("name", ""))
        if not r.get("brand"):  # brand_hint·API 둘 다 비었을 때만 최후 추정
            r["brand"] = guess_brand(r["name"])
        r.update(parse_variants(r["name"]))
        r["product_name"] = clean_product_name(r["name"], r.get("brand", ""))
        # 복합(세트/모음/도배) 여부 — 원본+정제명 기준. 시드에선 빼고 별도 시트로 격리.
        r["is_bundle"] = "Y" if is_composite(r["name"], r["product_name"]) else ""
    return rows
