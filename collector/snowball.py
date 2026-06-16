"""
눈덩이(snowball) 확장: 수집 결과에 등장한 '새 브랜드'를 다음 검색어로 재투입한다.

카테고리 검색('봉지라면' 등)으로 모은 상품에는 다양한 브랜드가 섞여 나온다.
그중 아직 검색어로 안 써본 브랜드를 빈도순으로 골라 재검색하면, 그 브랜드의
주력 제품(카테고리 상위 1000 밖에 있던 것 포함)까지 추가로 긁힌다.
"""

from __future__ import annotations

from collections import Counter


def candidate_brands(
    rows: list[dict],
    searched: set[str],
    min_count: int = 2,
    limit: int = 50,
) -> list[str]:
    """수집 행에서 아직 검색 안 한 브랜드를 빈도순으로 골라낸다.

    - min_count: 이 횟수 이상 등장한 브랜드만 (오타·잡음 브랜드 거르기)
    - limit:     이번 라운드에 재투입할 최대 브랜드 수 (API 호출량 가드)
    """
    searched_lower = {s.strip().lower() for s in searched if s}
    counts: Counter[str] = Counter()
    for r in rows:
        b = (r.get("brand") or "").strip()
        if b:
            counts[b] += 1

    out: list[str] = []
    for brand, c in counts.most_common():
        if c < min_count or brand.lower() in searched_lower:
            continue
        out.append(brand)
        if len(out) >= limit:
            break
    return out
