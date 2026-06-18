"""
변형(SKU) 단위 중복 제거.

네이버쇼핑은 같은 상품을 판매처마다 다른 product_id 로 올린다. 그래서 product_id
기준 dedup 만으로는 '농심 신라면 120g 5개입'이 판매처 수만큼 남는다. 시드 DB 에는
**변형(브랜드 + 제품명 + 용량 + 입수) 하나당 한 행**만 남기고, 판매처·가격·마케팅
문구 차이로 생긴 중복은 합친다.

대표 행 선택:
  - 인기순위(rank)가 가장 앞선(작은) 행을 대표로 남긴다.
  - 대표의 빈 필드는 버려지는 중복 행에서 메운다(백필) — 데이터 충실도↑.
  - 최저가(price)는 중복 중 최소값으로 채운다.

variant_key 는 dedup 뿐 아니라 실행 간 시판여부 추적(state.py)의 안정적 식별자로도
쓰인다. 판매처가 바뀌어 product_id 가 달라져도 같은 변형이면 같은 키를 갖는다.
"""

from __future__ import annotations

import re

# 브랜드 표기 잡음: (주)/㈜/주식회사/co·inc·ltd
_BRAND_NOISE = re.compile(r"\((?:주|유|사)\)|㈜|주식회사|\b(?:co|inc|ltd|corp)\b\.?", re.IGNORECASE)
_BRACKET = re.compile(r"[\[(\{][^\])\}]*[\])\}]")  # [..] (..) {..} 안쪽 통째로
# 용량/중량·입수 토큰 — 별도 키 성분이라 코어 이름에서 제거. (variants.py 와 같은 기준)
# 'x 5개입' / '120gx5' 같은 붙은 표기까지 통째로 걷어내도록 순서·경계를 맞춘다.
_VOL = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:kg|mg|ml|㎏|㎖|g|l|ℓ|리터|그램|키로)(?![a-wy-z])",
    re.IGNORECASE,
)
_PACK = re.compile(
    r"[x×*]?\s*\d+\s*(?:개입|입|개들이|개|봉지|봉|포|팩|캔|병|매|스틱|구|ea)"
    r"|[x×*]\s*\d+",
    re.IGNORECASE,
)
_PROMO = re.compile(r"\d\s*\+\s*\d")  # 1+1, 2+1
# 제품 식별과 무관한 마케팅/배송 잡음 (※ 맛·종류 단어는 절대 넣지 않는다)
_NOISE_WORDS = [
    "무료배송", "무배", "빠른배송", "당일발송", "당일출고", "오늘출발", "로켓배송",
    "행사", "특가", "할인", "사은품", "사은", "증정", "정품", "본사직영", "공식판매",
    "공식", "대용량", "기획", "이벤트", "best", "베스트", "신상", "new", "핫딜",
    "gift", "set", "멀티팩", "멀티",
]
_NOISE_RE = re.compile("|".join(re.escape(w) for w in _NOISE_WORDS), re.IGNORECASE)
# 형태/포장 토큰: '단독 토큰일 때만' 제거(포카칩의 '포' 같은 오삭제 방지).
# 변형 키는 브랜드+제품+용량+입수라 형태는 키에서 빼고 묶는다(컵/봉지는 보통 용량이 달라 구분됨).
_FORM_TOKENS = {
    "봉지", "봉", "컵", "캔", "병", "팩", "박스", "상자", "스틱", "포", "통",
    "큰사발", "왕뚜껑", "사발", "묶음", "낱개", "pet", "페트",
}
_TOKEN_SPLIT = re.compile(r"[^0-9a-z가-힣]+")
_NONWORD = re.compile(r"[^0-9a-z가-힣]+")

# 백필 대상(대표 행에 비었으면 중복에서 가져옴)
_BACKFILL = ["volume", "form", "pack_count", "is_limited", "brand",
             "category", "image", "link", "maker", "product_id"]


def _norm_brand(brand: str) -> str:
    b = _BRAND_NOISE.sub("", (brand or "").lower())
    return _NONWORD.sub("", b)


def _core_name(name: str, brand: str) -> str:
    """제품명에서 브랜드·용량·입수·형태·잡음·괄호를 걷어낸 핵심 토큰(맛/종류는 보존)."""
    s = (name or "").lower()
    nb = (brand or "").lower().strip()
    if nb and s.startswith(nb):
        s = s[len(nb):]
    s = _BRACKET.sub(" ", s)
    s = _VOL.sub(" ", s)
    s = _PACK.sub(" ", s)
    s = _PROMO.sub(" ", s)
    s = _NOISE_RE.sub(" ", s)
    if nb:
        s = s.replace(nb, " ")  # 이름 중간의 브랜드 재등장도 제거
    # 형태/포장 토큰은 '단독 토큰'일 때만 제거(포카칩의 '포' 등 오삭제 방지)
    tokens = [t for t in _TOKEN_SPLIT.split(s) if t and t not in _FORM_TOKENS]
    core = "".join(tokens)
    if not core:  # 다 걷어내 비면 브랜드 제거 전 이름으로 폴백 (서로 다른 제품 오병합 방지)
        core = _NONWORD.sub("", (name or "").lower())
    return core


def variant_key(row: dict) -> str:
    """브랜드 + 코어이름 + 용량 + 입수 → 변형 식별 키."""
    brand = _norm_brand(row.get("brand", ""))
    core = _core_name(row.get("name", ""), row.get("brand", ""))
    vol = (row.get("volume") or "").lower()
    pack = str(row.get("pack_count") or "")
    return f"{brand}|{core}|{vol}|{pack}"


def _rank_val(r: dict) -> int:
    try:
        return int(r.get("rank") or 10**9)
    except (TypeError, ValueError):
        return 10**9


def _min_price(a: dict, b: dict) -> str:
    """두 행의 최저가(빈/비정상 값은 무시)."""
    vals = []
    for r in (a, b):
        try:
            p = int(str(r.get("price") or "").strip())
            if p > 0:
                vals.append(p)
        except (TypeError, ValueError):
            pass
    return str(min(vals)) if vals else (a.get("price") or b.get("price") or "")


def dedup(rows: list[dict]) -> list[dict]:
    """변형(SKU) 단위 중복 제거. 등장 순서를 유지하고 대표 1행만 남긴다."""
    best: dict[str, dict] = {}
    order: list[str] = []
    for r in rows:
        k = variant_key(r)
        r["variant_key"] = k
        cur = best.get(k)
        if cur is None:
            best[k] = r
            order.append(k)
            continue
        # 인기순위가 더 앞선(작은) 행을 대표로
        keep, drop = (r, cur) if _rank_val(r) < _rank_val(cur) else (cur, r)
        for f in _BACKFILL:
            if not keep.get(f) and drop.get(f):
                keep[f] = drop[f]
        keep["price"] = _min_price(keep, drop)
        keep["variant_key"] = k
        best[k] = keep
    return [best[k] for k in order]
