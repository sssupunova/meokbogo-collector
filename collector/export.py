"""수집 결과를 xlsx 또는 csv 로 저장."""

from __future__ import annotations

import csv

# 상세(SKU) 출력 컬럼 — 브랜드·정제제품명·원본상품명·변형속성을 앞에, 추적 필드를 뒤에
COLUMNS = [
    "brand", "product_name", "is_bundle", "name",
    "volume", "form", "pack_count", "is_limited",
    "price", "mall", "category", "rank",
    "image", "link", "product_id", "source", "keyword",
    "is_new", "first_seen", "last_seen", "sale_status", "collected_at",
]
HEADERS_KR = [
    "브랜드", "제품명", "묶음", "원본상품명",
    "용량중량", "형태", "입수", "한정",
    "가격", "판매처", "카테고리", "인기순위",
    "이미지", "링크", "상품ID", "출처", "검색어",
    "신규", "최초수집일", "최종확인일", "판매상태", "수집일시",
]

# 제품 단위 distilled('브랜드 + 제품명'만 추린 시드) 출력 컬럼
COLUMNS_SEED = ["brand", "product_name", "category", "variant_count",
                "min_price", "image", "link"]
HEADERS_SEED = ["브랜드", "제품명", "카테고리", "변형수", "최저가", "대표이미지", "대표링크"]


def to_csv(rows: list[dict], path: str, columns=COLUMNS, headers=HEADERS_KR) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(headers)
        for r in rows:
            w.writerow([r.get(c, "") for c in columns])


def to_xlsx(rows: list[dict], path: str, columns=COLUMNS, headers=HEADERS_KR) -> None:
    try:
        from openpyxl import Workbook
    except ImportError as e:  # pragma: no cover
        raise SystemExit(
            "xlsx 출력에는 openpyxl 이 필요합니다:  pip install openpyxl\n"
            "또는 --format csv 로 저장하세요."
        ) from e

    wb = Workbook()
    ws = wb.active
    ws.title = "products"
    ws.append(headers)
    for r in rows:
        ws.append([r.get(c, "") for c in columns])
    wb.save(path)


def save(rows: list[dict], path: str, fmt: str,
         columns=COLUMNS, headers=HEADERS_KR) -> None:
    if fmt == "csv":
        to_csv(rows, path, columns, headers)
    elif fmt == "xlsx":
        to_xlsx(rows, path, columns, headers)
    else:
        raise ValueError(f"지원하지 않는 형식: {fmt}")


def save_seed(seed_rows: list[dict], path: str, fmt: str) -> None:
    """제품 단위 distilled('브랜드 + 제품명') 시드 저장."""
    save(seed_rows, path, fmt, COLUMNS_SEED, HEADERS_SEED)
