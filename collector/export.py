"""수집 결과를 xlsx 또는 csv 로 저장."""

from __future__ import annotations

import csv

# 출력 컬럼 순서 (브랜드·상품명·변형속성을 앞에)
COLUMNS = [
    "brand", "name", "volume", "form", "pack", "limited",
    "price", "mall", "category", "image", "link", "product_id",
    "status", "source", "keyword", "collected_at", "last_seen",
]
HEADERS_KR = [
    "브랜드", "상품명", "용량/중량", "형태", "입수", "한정",
    "가격", "판매처", "카테고리", "이미지", "링크", "상품ID",
    "판매상태", "출처", "검색어", "수집일시", "최종확인",
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


_KR_TO_KEY = dict(zip(HEADERS_KR, COLUMNS))


def load(path: str) -> list[dict]:
    """이전에 저장한 csv/xlsx 를 다시 행 dict 리스트로 읽는다 (병합용).

    한글 헤더를 내부 키로 되돌린다. 모르는 컬럼/구버전 파일도 최대한 살린다.
    """
    rows: list[dict] = []
    if path.endswith(".csv"):
        with open(path, encoding="utf-8-sig", newline="") as f:
            for d in csv.DictReader(f):
                rows.append({_KR_TO_KEY.get(k, k): (v or "") for k, v in d.items()})
        return rows

    from openpyxl import load_workbook

    wb = load_workbook(path, read_only=True, data_only=True)
    ws = wb.active
    it = ws.iter_rows(values_only=True)
    headers = next(it, None)
    if headers:
        keys = [_KR_TO_KEY.get(h, h) for h in headers]
        for vals in it:
            rows.append({k: ("" if v is None else v) for k, v in zip(keys, vals)})
    return rows


def save(rows: list[dict], path: str, fmt: str) -> None:
    if fmt == "csv":
        to_csv(rows, path)
    elif fmt == "xlsx":
        to_xlsx(rows, path)
    else:
        raise ValueError(f"지원하지 않는 형식: {fmt}")
