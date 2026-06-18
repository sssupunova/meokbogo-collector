"""
브랜드 리스트(CSV) → 검색어 자동 생성기.

핵심 설계(이게 제일 중요):
  검색어를 '제품명'으로 시딩하면 순환논리가 된다. 식약처 DB가 빠뜨린 제품은
  제품명 목록에도 없기 때문이다. → 검색 단위를 '브랜드 + 카테고리'로 올린다.
  브랜드는 유한하고 식약처와 독립된 축이라, "농심 라면"으로 인기순 검색하면
  그 브랜드의 실제 주력 제품(식약처가 빠뜨린 것 포함)이 나온다.

CSV(data/kr_food_brands_db.csv) 컬럼:
  type                manufacturer | franchise
  category            가공식품 | 프랜차이즈
  subcategory         라면 / 스낵 / 커피 ...           ← 카테고리 축
  company_name        농심, 오뚜기                      ← manufacturer의 검색 브랜드
  company_legal_name  (주)농심
  brand_name          신라면(=제품명!) / 빽다방(=franchise 소비자 브랜드)
  note                라면 / 컵라면 / 매출1위 ...        (자유 텍스트, 비어 있기도 함)

검색 브랜드(search_brand) 도출 — type 에 따라 다르다:
  manufacturer → company_name  (brand_name 은 제품명이라 키워드로 쓰면 순환논리!)
  franchise    → brand_name    (빽다방 등 소비자 인지 브랜드가 company_name 보다 검색성↑)
"""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

# CSV 가 카테고리 컬럼(subcategory)을 들고 있으므로 brand_x_category 가 곧 owncat
# (행 자기 카테고리하고만 곱함 → "농심 김치" 같은 헛검색이 안 생긴다).
GEN_MODES = ("brand_x_category", "brand_only")
TYPE_FILTERS = ("manufacturer", "franchise", "all")

MAX_DISPLAY = 100   # navershop API 한 페이지 최대
MAX_ITEMS = 1000    # navershop 검색어당 최대 (호출 예산 추정용)


@dataclass
class Brand:
    type: str
    category: str
    subcategory: str
    company_name: str
    company_legal_name: str
    brand_name: str
    note: str

    @property
    def search_brand(self) -> str:
        """검색에 쓸 브랜드명. manufacturer 는 회사명, franchise 는 소비자 브랜드."""
        if self.type == "franchise":
            return (self.brand_name or self.company_name).strip()
        return (self.company_name or self.brand_name).strip()


def load_brands(csv_path, type_filter: str = "manufacturer") -> list[Brand]:
    """브랜드 CSV 를 읽어 Brand 리스트로. type_filter 로 manufacturer/franchise/all 선별."""
    path = Path(csv_path)
    if not path.exists():
        raise FileNotFoundError(f"브랜드 CSV 가 없습니다: {path}")
    if type_filter not in TYPE_FILTERS:
        raise ValueError(f"알 수 없는 type: {type_filter!r} (가능: {', '.join(TYPE_FILTERS)})")

    brands: list[Brand] = []
    with path.open(encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            b = Brand(
                type=(row.get("type") or "").strip(),
                category=(row.get("category") or "").strip(),
                subcategory=(row.get("subcategory") or "").strip(),
                company_name=(row.get("company_name") or "").strip(),
                company_legal_name=(row.get("company_legal_name") or "").strip(),
                brand_name=(row.get("brand_name") or "").strip(),
                note=(row.get("note") or "").strip(),
            )
            if type_filter != "all" and b.type != type_filter:
                continue
            if not b.search_brand:
                continue
            brands.append(b)
    return brands


def generate_keywords(
    brands: list[Brand],
    mode: str = "brand_x_category",
    limit: int | None = None,
    extra_brands=None,
) -> list[str]:
    """브랜드 리스트 → 검색어 리스트 (등장 순서 유지, 대소문자 무시 dedup).

    mode:
      brand_x_category  "농심 라면"   — 행 자기 subcategory 와 곱함 (기본·권장)
      brand_only        "농심"        — 호출 적고 가장 넓게, 인기순으로 주력 제품 훑기
    extra_brands:
      눈덩이(snowball) 확장용 추가 브랜드명(문자열) iterable. brand_only 로 합류한다.
      수집 결과에서 발견된 신규 브랜드를 같은 함수로 재투입하기 위한 통로(3번 기능 공유).
    limit:
      생성 검색어 상한. CSV 가 이미 매출·순위로 큐레이션돼 있어 앞에서부터 자른다.
    """
    if mode not in GEN_MODES:
        raise ValueError(f"알 수 없는 mode: {mode!r} (가능: {', '.join(GEN_MODES)})")

    keywords: list[str] = []
    seen: set[str] = set()

    def add(kw: str) -> None:
        kw = " ".join((kw or "").split())  # 공백 정리
        key = kw.lower()
        if kw and key not in seen:
            seen.add(key)
            keywords.append(kw)

    for b in brands:
        brand = b.search_brand
        if not brand:
            continue
        if mode == "brand_only":
            add(brand)
        else:  # brand_x_category
            cat = b.subcategory
            add(f"{brand} {cat}" if cat else brand)

    for name in (extra_brands or []):
        add(str(name))

    if limit is not None:
        keywords = keywords[:limit]
    return keywords


def estimate_calls(n_keywords: int, max_items: int = MAX_ITEMS) -> int:
    """검색어 N개 수집 시 예상 API 호출 수 (하루 25,000 한도 가늠용)."""
    pages = (min(max_items, MAX_ITEMS) + MAX_DISPLAY - 1) // MAX_DISPLAY
    return n_keywords * pages
