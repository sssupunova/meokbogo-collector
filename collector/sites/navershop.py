"""
네이버쇼핑 검색 API 어댑터.

네이버 개발자센터(https://developers.naver.com)에서 애플리케이션을 등록하고
'검색' API를 추가하면 Client ID / Secret 을 받는다. 그걸 환경변수로 넣어 쓴다.

  NAVER_CLIENT_ID, NAVER_CLIENT_SECRET

API 사양 요약:
  GET https://openapi.naver.com/v1/search/shop.json
  params: query(검색어), display(최대 100), start(1~1000), sort(sim|date|asc|dsc)
  헤더:   X-Naver-Client-Id, X-Naver-Client-Secret
  한계:   검색어당 최대 1000건(100 x 10페이지), 하루 25,000건 호출
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

import requests

API_URL = "https://openapi.naver.com/v1/search/shop.json"
SOURCE = "navershop"

MAX_DISPLAY = 100   # API가 허용하는 한 페이지 최대 개수
MAX_START = 1000    # API가 허용하는 start 상한 → 검색어당 최대 1000건


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def search(
    keyword: str,
    client_id: str,
    client_secret: str,
    max_items: int = MAX_START,
    sort: str = "sim",
    delay: float = 0.3,
    timeout: float = 10.0,
    session: requests.Session | None = None,
    brand_hint: str = "",
):
    """검색어 하나로 네이버쇼핑을 페이지네이션하며 상품을 모은다.

    반환: list[dict] — 각 dict는 brand/name/maker/price/mall/image/link/...
    """
    sess = session or requests.Session()
    headers = {
        "X-Naver-Client-Id": client_id,
        "X-Naver-Client-Secret": client_secret,
    }

    rows: list[dict] = []
    start = 1
    cap = min(max_items, MAX_START)

    while start <= cap:
        display = min(MAX_DISPLAY, cap - start + 1)
        resp = sess.get(
            API_URL,
            headers=headers,
            params={"query": keyword, "display": display, "start": start, "sort": sort},
            timeout=timeout,
        )
        if resp.status_code != 200:
            raise RuntimeError(
                f"네이버 API 오류 {resp.status_code} (keyword={keyword!r}): {resp.text[:200]}"
            )

        items = resp.json().get("items", [])
        if not items:
            break

        for offset, it in enumerate(items):
            # rank = 검색 결과 내 위치(1-base) = 인기/관련도 신호.
            # 네이버 Open API 에는 '랭킹순' 정렬이 없어, sort 결과의 순서를 신호로 캡처한다.
            rows.append(_to_row(it, keyword, rank=start + offset, brand_hint=brand_hint))

        if len(items) < display:
            break  # 마지막 페이지

        start += display
        time.sleep(delay)  # 매너용 지연 (rate limit 보호)

    return rows


def _to_row(item: dict, keyword: str, rank: int, brand_hint: str = "") -> dict:
    """네이버 API item → 공통 행 스키마. clean 단계에서 title 태그·변형속성을 처리한다.

    brand: brand_hint(검색어의 브랜드)가 있으면 그걸 우선한다. 브랜드 타깃 검색이라
    검색어 브랜드가 가장 신뢰도 높고(예: '삼양식품 라면'→삼양식품), 네이버가 brand
    필드를 비우거나 서브라인('신라면'·'맵탱')을 넣는 오염을 함께 막는다. 원본 brand/maker
    는 maker 필드에 남겨 감사용으로 보존. hint 없으면(수동 검색어) API brand→maker 순.
    """
    now = _now_iso()
    api_brand = (item.get("brand") or item.get("maker") or "").strip()
    return {
        "source": SOURCE,
        "keyword": keyword,
        "rank": rank,
        "brand": brand_hint.strip() or api_brand,
        "name": item.get("title", ""),          # <b> 태그 포함 — clean.py에서 제거
        "maker": (item.get("maker") or "").strip(),
        "price": item.get("lprice", ""),
        "mall": item.get("mallName", ""),
        "category": " > ".join(
            c for c in (
                item.get("category1"), item.get("category2"),
                item.get("category3"), item.get("category4"),
            ) if c
        ),
        "image": item.get("image", ""),
        "link": item.get("link", ""),
        "product_id": item.get("productId", ""),
        # 시판여부 추적용. --state 없이 단일 실행이면 셋 다 '이번 수집' 기준.
        "is_new": "",            # 신규 발견 여부 (state 비교 시 채움)
        "first_seen": now,       # 최초 수집일
        "last_seen": now,        # 최종 확인일
        "sale_status": "판매중",  # API 결과에 있다 = 현재 판매중
        "collected_at": now,
    }
