"""
도메인 프로파일(중앙 설정) — 다른 키워드/도메인에서도 재사용하기 위한 설정 레이어.

지금까지 코드에 흩어져 있던 '도메인 특화 값'(브랜드 CSV·컬럼매핑, 정제 잡음어,
카테고리/형태 사전, 세트 마커, 시드 파일명)을 한곳(DEFAULTS=kfood)에 모았다.
profiles/<name>.json 또는 경로로 일부만 덮어쓰면 다른 도메인용 프로파일이 된다.

  - 식품 외 다른 카테고리/브랜드 리스트로 쓰기  → 프로파일만 추가 (도메인 일반화의 토대)
  - 나중에 GUI/웹                              → 이 프로파일을 고르고 실행시키면 됨

run.py 가 시작할 때 use(profile) 를 호출하면 clean/variants/dedup 모듈의 패턴이
그 프로파일로 재구성된다(모듈 임포트 시엔 DEFAULTS 로 구성되어 단독으로도 동작).
"""

from __future__ import annotations

import json
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
PROFILES_DIR = _ROOT / "profiles"

# ── 기본 프로파일 (= 현재 K-Food/먹보고 동작) ────────────────────────────
DEFAULTS: dict = {
    "name": "kfood",
    "description": "K-Food 가공식품 (먹보고)",

    # 검색어 생성 (keywords_gen)
    "brands_csv": str(_ROOT / "data" / "kr_food_brands_db.csv"),
    "brand_columns": {  # 내부 필드 ← CSV 헤더명 (다른 CSV 구조도 매핑만 바꾸면 됨)
        "type": "type", "category": "category", "subcategory": "subcategory",
        "company_name": "company_name", "company_legal_name": "company_legal_name",
        "brand_name": "brand_name", "note": "note",
    },
    "type_filter": "manufacturer",   # manufacturer | franchise | all (식품 외엔 보통 all)
    "gen_mode": "brand_x_category",  # brand_x_category | brand_only

    # 출력 (run/export)
    "seed_filename": "먹보고_최종DB시드",  # 최종 DB 시드 파일명(폴더에서 튀게)

    # 제품명 정제 — SEO/포장 잡음어 (clean.clean_product_name). 맛/종류 단어는 넣지 말 것.
    "name_noise": [
        "봉지라면", "컵라면", "봉지면", "박스라면", "한박스", "업소용", "즉석라면", "매운라면",
        "끓여먹는라면", "끓여먹는", "간편조리", "간편식", "즉석식품", "자취요리", "비상식량",
        "혼밥요리", "간단요리", "봉다리라면", "봉다리", "국물라면", "인스턴트", "식자재마트",
        "식자재", "선물용", "야식", "간식", "캠핑", "혼밥", "자취", "비상", "비축", "사재기",
        "도매", "대량", "벌크", "박스째", "낱개", "묶음", "박스", "봉지", "한봉지", "면류",
        "라면류", "먹거리", "다양한", "탕비실", "사무실", "단체", "선물", "각종", "끓이는",
        "즉석", "ramyeon", "ramen", "품질", "정품", "무료", "행사", "특가", "사은품", "증정",
        "best", "신상", "핫딜",
    ],

    # 복합(세트/모음) 검출 (clean.is_composite)
    "set_markers": ["세트", "모음", "꾸러미", "패키지", "종합선물"],  # 리터럴 마커(정규식 특수문자는 코드 고정)
    "composite_min_tokens": 6,

    # 변형 단위 중복 제거 코어 정규화 잡음어 (dedup)
    "dedup_noise": [
        "무료배송", "무배", "빠른배송", "당일발송", "당일출고", "오늘출발", "로켓배송",
        "행사", "특가", "할인", "사은품", "사은", "증정", "정품", "본사직영", "공식판매",
        "공식", "대용량", "기획", "이벤트", "best", "베스트", "신상", "new", "핫딜",
        "gift", "set", "멀티팩", "멀티",
    ],
    # 형태/포장 토큰 — '단독 토큰'일 때만 제거 (dedup 코어 키에서 형태는 뺀다)
    "form_tokens": [
        "봉지", "봉", "컵", "캔", "병", "팩", "박스", "상자", "스틱", "포", "통",
        "큰사발", "왕뚜껑", "사발", "묶음", "낱개", "pet", "페트",
    ],

    # 변형속성 파싱 (variants/dedup) — 용량/입수 단위. 도메인마다 다르다(식품 g·개입 ↔ 건기식 정·개월분).
    # ※ 정규식 alternation 이라 긴/구체 단위를 앞에 둘 것 (개월분 → 개월 → 개).
    "volume_units": ["kg", "mg", "ml", "㎏", "㎖", "g", "l", "ℓ", "리터", "그램", "키로"],
    "pack_units": ["개입", "입", "개들이", "개", "봉지", "봉", "포", "팩", "캔", "병",
                   "매", "스틱", "구", "ea"],
    "variant_forms": [   # [표시형태, [매칭 토큰...]] — 위에서부터 먼저 매치
        ["컵", ["컵라면", "큰사발", "왕뚜껑", "사발", "컵"]],
        ["캔", ["캔"]],
        ["병", ["페트", "pet", "병"]],
        ["스틱", ["스틱", "stick"]],
        ["파우치", ["파우치", "스파우트"]],
        ["박스", ["박스", "박스형", "상자", "box"]],
        ["팩", ["멀티팩", "팩"]],
        ["봉지", ["봉지", "봉입", "봉"]],
        ["포", ["포"]],
        ["통", ["통"]],
    ],
    "limited_words": [
        "한정판", "한정", "에디션", "edition", "콜라보레이션", "콜라보", "collab",
        "리미티드", "limited",
    ],
}

# 현재 활성 프로파일 (use() 로 교체)
ACTIVE: dict = dict(DEFAULTS)


def _merge(base: dict, over: dict) -> dict:
    """over 를 base 위에 얕게 병합하되 brand_columns 는 키 단위로 병합."""
    out = dict(base)
    for k, v in over.items():
        if k == "brand_columns" and isinstance(v, dict):
            bc = dict(base.get("brand_columns", {}))
            bc.update(v)
            out[k] = bc
        else:
            out[k] = v
    return out


def load(name_or_path: str | None) -> dict:
    """프로파일 로드 — 빌트인 이름(profiles/<name>.json) 또는 파일 경로. DEFAULTS 위에 병합."""
    if not name_or_path or name_or_path == "kfood":
        return dict(DEFAULTS)
    p = Path(name_or_path)
    if not p.exists():
        cand = PROFILES_DIR / f"{name_or_path}.json"
        if cand.exists():
            p = cand
        else:
            raise FileNotFoundError(
                f"프로파일을 찾을 수 없습니다: {name_or_path} "
                f"(profiles/{name_or_path}.json 또는 경로)"
            )
    data = json.loads(p.read_text(encoding="utf-8"))
    return _merge(DEFAULTS, data)


def use(cfg: dict) -> None:
    """활성 프로파일을 적용하고 각 모듈의 패턴을 재구성한다."""
    global ACTIVE
    ACTIVE = cfg
    from collector import clean, variants, dedup  # 지연 임포트(순환 방지)
    variants.configure(cfg)
    dedup.configure(cfg)
    clean.configure(cfg)


def get() -> dict:
    return ACTIVE
