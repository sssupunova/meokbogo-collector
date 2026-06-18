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
# 숫자 + 단위. 첫 매치를 단위 1개분 크기로 본다("120g x 5" → 120g).
# 단위 뒤 (?![a-wy-z]) : 'g'/'l' 같은 한 글자 단위가 'x'(묶음표시)나 한글 앞에 와도
# 매치되게 하되, 'gallon' 처럼 다른 영문 단위로 이어지는 경우는 배제한다. ('120gx5' → 120g)
_VOLUME_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(kg|mg|ml|㎏|㎖|g|l|ℓ|리터|그램|키로)(?![a-wy-z])",
    re.IGNORECASE,
)
_UNIT_NORM = {
    "kg": "kg", "㎏": "kg", "키로": "kg",
    "g": "g", "그램": "g", "mg": "mg",
    "l": "L", "ℓ": "L", "리터": "L",
    "ml": "ml", "㎖": "ml",
}

# ── 형태 ──────────────────────────────────────────────────
# config(variant_forms)에서 구성. 우선순위 순서대로 검사하고 첫 매치를 채택.
_FORMS: list = []

# ── 입수(묶음 개수) ───────────────────────────────────────
# "5개입 / 5입 / 5개 / 30봉 / 20포 / 12캔 ..." 와 "x5 / ×20" 패턴.
_PACK_SUFFIX_RE = re.compile(
    r"(\d+)\s*(?:개입|입|개들이|개|봉지|봉|포|팩|캔|병|매|스틱|구|ea)\b",
    re.IGNORECASE,
)
_PACK_X_RE = re.compile(r"[x×*]\s*(\d+)\s*(?:개|입|봉|포|팩|캔|병)?\b", re.IGNORECASE)

# ── 한정/에디션 ───────────────────────────────────────────
_LIMITED_RE = None  # config(limited_words)에서 구성


def configure(cfg: dict) -> None:
    """프로파일에서 형태 사전·한정 단어를 (재)구성한다."""
    global _FORMS, _LIMITED_RE
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
