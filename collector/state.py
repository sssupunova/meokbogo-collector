"""
실행 간 시판여부 추적 (선택적, --state 로 켠다).

크롤러의 가치는 last_seen·시판여부·신제품 발견에 있다. 단일 실행만으로는
'언제 처음 봤는지/지금도 파는지/이번에 새로 나왔는지'를 알 수 없으므로,
product_id 별 마지막 스냅샷을 JSON 으로 들고 다니며 실행 간 비교한다.

  - 이전에 본 적 있는 상품  → first_seen 보존, last_seen 갱신, 판매중
  - 이번에 처음 본 상품      → is_new=Y (신제품 발견)
  - 예전엔 봤는데 이번엔 없는 상품 → 판매상태 '미확인'(단종/판매중단 후보)으로 재출력

상태 파일이 없으면 이 단계는 통째로 생략되고, 각 행은 이번 수집 기준값만 갖는다.
"""

from __future__ import annotations

import json
from pathlib import Path

from collector.export import COLUMNS


def load_state(path) -> dict[str, dict]:
    """product_id → 마지막 스냅샷(dict). 파일 없으면 빈 dict."""
    p = Path(path)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _snapshot(row: dict) -> dict:
    """state 에 저장할 컬럼만 추린 스냅샷 (재출력 가능하도록 COLUMNS 전체)."""
    return {c: row.get(c, "") for c in COLUMNS}


def apply_state(rows: list[dict], state: dict, now: str):
    """이번 수집 rows 를 이전 state 와 대조한다.

    반환: (out_rows, new_state, stats)
      out_rows  — 이번 수집 행 + 사라진 행('미확인')
      new_state — 갱신된 product_id → 스냅샷
      stats     — {"new", "seen", "missing"}
    """
    new_state = dict(state)
    current: set[str] = set()
    out: list[dict] = []
    n_new = n_seen = 0

    for r in rows:
        pid = (r.get("product_id") or "").strip()
        if not pid:
            out.append(r)  # 식별 불가 → 추적 제외, 그대로 통과
            continue
        current.add(pid)
        prev = state.get(pid)
        if prev:
            r["first_seen"] = prev.get("first_seen", r.get("first_seen", now))
            r["is_new"] = ""
            n_seen += 1
        else:
            r["is_new"] = "Y"
            r["first_seen"] = now  # 신규: 이번 run 의 now 로 통일
            n_new += 1
        r["last_seen"] = now
        r["sale_status"] = "판매중"
        new_state[pid] = _snapshot(r)
        out.append(r)

    # 이전엔 봤는데 이번 수집에 없는 상품 → '미확인'으로 재출력 + 상태 보존
    n_missing = 0
    for pid, snap in state.items():
        if pid in current:
            continue
        miss = dict(snap)
        miss["is_new"] = ""
        miss["sale_status"] = "미확인"
        out.append(miss)
        new_state[pid] = miss
        n_missing += 1

    return out, new_state, {"new": n_new, "seen": n_seen, "missing": n_missing}


def save_state(path, state: dict) -> None:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(state, ensure_ascii=False, indent=0), encoding="utf-8")
