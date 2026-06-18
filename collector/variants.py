"""
상품명(title)에서 변형 속성을 휴리스틱으로 뽑아낸다.

크롤러의 가치 중 하나가 '변형 속성'(같은 제품의 용량/형태/입수 차이)이다.
바코드 같은 골든키는 못 얻지만, title 에 녹아 있는 아래 신호는 파싱할 수 있다.

  volume      용량/중량   "120g", "1.5L", "500ml"        (단위 1개분 크기)
  form        형태        봉지 / 컵 / 캔 / 병 / 팩 / 박스 / 스틱 / 포 / 통
  pack_count  입수        몇 개 묶음인지 (정수)  "5개입", "x20", "30봉"
  is_limited  한정여부    한정/에디션/콜라보 등 → "Y"

정확 파싱이 아니라 휴리스틱이다(완벽하지 않음). 무거운 정규화는 먹보고 앱 쪽에서.
"""

from __future__ import annotations

import re

from collector import config

# ── 용량/중량 ─────────────────────────────────────────────
# 용량/입수 단위·형태 사전·한정 단어는 config 에서 구성. (도메인마다 단위가 다르다)
_UNIT_NORM = {  # 표기 정규화(매핑에 없으면 소문자 그대로)
    "kg": "kg", "㎏": "kg", "키로": "kg",
    "g": "g", "그램": "g", "mg": "mg",
    "l": "L", "ℓ": "L", "리터": "L",
    "ml": "ml", "㎖": "ml",
}
_VOLUME_RE = None      # 숫자+용량단위 (그룹 1=양, 2=단위)
_FORMS: list = []      # 형태 사전
_PACK_SUFFIX_RE = None  # 숫자+입수단위
_PACK_X_RE = re.compile(r"[x×*]\s*(\d+)\s*(?:개|입|봉|포|팩|캔|병)?\b", re.IGNORECASE)
_LIMITED_RE = None     # 한정/에디션


def configure(cfg: dict) -> None:
    """프로파일에서 용량/입수 단위·형태 사전·한정 단어를 (재)구성한다."""
    global _VOLUME_RE, _PACK_SUFFIX_RE, _FORMS, _LIMITED_RE
    vol = "|".join(cfg.get("volume_units", []))
    # 단위 뒤 (?![a-wy-z]): 'g'/'l' 한 글자 단위가 'x'·한글 앞이어도 매치, 'gallon' 류는 배제
    _VOLUME_RE = re.compile(rf"(\d+(?:[.,]\d+)?)\s*({vol})(?![a-wy-z])", re.IGNORECASE)
    pack = "|".join(cfg.get("pack_units", []))
    _PACK_SUFFIX_RE = re.compile(rf"(\d+)\s*(?:{pack})\b", re.IGNORECASE)
    _FORMS = [(label, tuple(tokens)) for label, tokens in cfg.get("variant_forms", [])]
    words = cfg.get("limited_words", [])
    _LIMITED_RE = re.compile("|".join(re.escape(w) for w in words), re.IGNORECASE) if words \
        else re.compile(r"(?!x)x")  # 매치 안 되는 패턴


def parse_volume(title: str) -> str:
    m = _VOLUME_RE.search(title or "")
    if not m:
        return ""
    amount = m.group(1).replace(",", ".")
    # 정수면 소수점 제거(120.0 → 120)
    if amount.endswith(".0"):
        amount = amount[:-2]
    unit = _UNIT_NORM.get(m.group(2).lower(), m.group(2).lower())
    return f"{amount}{unit}"


def parse_form(title: str) -> str:
    t = title or ""
    for form, tokens in _FORMS:
        if any(tok in t.lower() if tok.isascii() else tok in t for tok in tokens):
            return form
    return ""


def parse_pack_count(title: str) -> str:
    """입수 개수(정수 문자열). 못 찾으면 ""."""
    t = title or ""
    counts = [int(m.group(1)) for m in _PACK_SUFFIX_RE.finditer(t)]
    counts += [int(m.group(1)) for m in _PACK_X_RE.finditer(t)]
    # 1은 보통 의미 없고(1개/1봉), 비정상적으로 큰 값은 용량 오인일 수 있어 버린다.
    counts = [c for c in counts if 1 < c <= 200]
    return str(max(counts)) if counts else ""


def parse_limited(title: str) -> str:
    return "Y" if _LIMITED_RE.search(title or "") else ""


def parse_variants(title: str) -> dict:
    """title → {volume, form, pack_count, is_limited}. 행에 그대로 merge 한다."""
    return {
        "volume": parse_volume(title),
        "form": parse_form(title),
        "pack_count": parse_pack_count(title),
        "is_limited": parse_limited(title),
    }


configure(config.DEFAULTS)  # 임포트 시 기본 프로파일로 구성 (use() 가 나중에 덮음)
