"""수집 결과를 xlsx 또는 csv 로 저장."""

from __future__ import annotations

import csv

# 출력 컬럼 순서 (브랜드·상품명을 앞에)
COLUMNS = [
    "brand", "name", "price", "mall", "category",
    "image", "link", "product_id", "source", "keyword", "collected_at",
]
HEADERS_KR = [
    "브랜드", "상품명", "가격", "판매처", "카테고리",
    "이미지", "링크", "상품ID", "출처", "검색어", "수집일시",
]


def to_csv(rows: list[dict], path: str) -> None:
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(HEADERS_KR)
        for r in rows:
            w.writerow([r.get(c, "") for c in COLUMNS])


def to_xlsx(rows: list[dict], path: str) -> None:
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
    ws.append(HEADERS_KR)
    for r in rows:
        ws.append([r.get(c, "") for c in COLUMNS])
    wb.save(path)


def save(rows: list[dict], path: str, fmt: str) -> None:
    if fmt == "csv":
        to_csv(rows, path)
    elif fmt == "xlsx":
        to_xlsx(rows, path)
    else:
        raise ValueError(f"지원하지 않는 형식: {fmt}")
