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
# 여러 제품을 묶은 번들/모음 (단일 제품 아님 → 시드에서 제외). 1+1 같은 행사는 제외하고 검출.
_BUNDLE_RE = re.compile(r"[+＋]|외\s*\d+\s*종|골라\s*담|모음전|맛\s*골라")


def strip_title(title: str) -> str:
    """<b> 태그 제거 + HTML 엔티티 복원 + 공백 정리."""
    text = _TAG_RE.sub("", title or "")
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def guess_brand(name: str) -> str:
    """브랜드 필드가 비었을 때 상품명 앞 단어로 추정 (최후 보정용, 완벽하지 않음)."""
    parts = (name or "").split()
    return parts[0] if parts else ""


def clean_product_name(name: str, brand: str) -> str:
    """판매처 제목에서 군더더기를 걷어낸 '읽을 수 있는 제품명'(브랜드 포함).

    용량·입수·괄호·마케팅 문구·구분자를 제거하되 맛/종류/형태는 살린다.
    결과가 브랜드로 시작하지 않으면 브랜드를 앞에 붙인다. (예: '신라면' → '농심 신라면')
    """
    s = name or ""
    s = _d._BRACKET.sub(" ", s)
    s = _d._VOL.sub(" ", s)
    s = _d._PACK.sub(" ", s)
    s = _d._PROMO.sub(" ", s)
    s = _d._NOISE_RE.sub(" ", s)
    s = _SEP_RE.sub(" ", s)
    s = _SPACE_RE.sub(" ", s).strip(" -·")
    b = (brand or "").strip()
    if b and not s.lower().startswith(b.lower()):
        s = f"{b} {s}".strip()
    return s


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
        # 번들 검출은 1+1 행사가 이미 제거된 정제 제품명 기준 (행사 오검출 방지)
        r["is_bundle"] = "Y" if _BUNDLE_RE.search(r["product_name"]) else ""
    return rows
