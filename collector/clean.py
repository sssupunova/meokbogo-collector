"""
수집 결과 정제: 상품명 태그 제거 + 브랜드 보정 + 중복 제거.

먹보고 DB에 넣기 전 '브랜드 + 상품명'을 사람이 보기 좋은 형태로 1차 정리하는 단계.
무거운 정규화(패밀리/폼/카테고리 5버킷)는 먹보고 앱 쪽 파이프라인에서 하므로 여기선 가볍게.
"""

from __future__ import annotations

import html
import re

from collector.variants import parse_variants

_TAG_RE = re.compile(r"</?b>", re.IGNORECASE)
_SPACE_RE = re.compile(r"\s+")


def strip_title(title: str) -> str:
    """<b> 태그 제거 + HTML 엔티티 복원 + 공백 정리."""
    text = _TAG_RE.sub("", title or "")
    text = html.unescape(text)
    return _SPACE_RE.sub(" ", text).strip()


def guess_brand(name: str) -> str:
    """브랜드 필드가 비었을 때 상품명 앞 단어로 추정 (보정용, 완벽하지 않음)."""
    parts = (name or "").split()
    return parts[0] if parts else ""


def clean_rows(rows: list[dict]) -> list[dict]:
    """행 리스트를 정제한다. (원본 변형 — 같은 객체를 갱신)"""
    for r in rows:
        r["name"] = strip_title(r.get("name", ""))
        if not r.get("brand"):
            r["brand"] = guess_brand(r["name"])
        # 상품명에서 변형속성(용량/형태/입수/한정) 추출 — 이미 있으면 덮지 않음
        for k, v in parse_variants(r["name"]).items():
            r.setdefault(k, v)
    return rows


def _dedup_key(r: dict) -> str:
    """중복 판단 키: product_id 우선, 없으면 브랜드+상품명 소문자."""
    pid = (r.get("product_id") or "").strip()
    if pid:
        return f"pid:{pid}"
    return f"name:{r.get('brand', '').lower()}|{r.get('name', '').lower()}"


def dedup(rows: list[dict]) -> list[dict]:
    """같은 상품 중복 제거. 먼저 등장한 행을 유지한다."""
    seen: set[str] = set()
    out: list[dict] = []
    for r in rows:
        key = _dedup_key(r)
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out
