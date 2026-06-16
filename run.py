#!/usr/bin/env python3
"""
먹보고 상품 수집기 — 네이버쇼핑에서 브랜드·상품명을 모아 엑셀/CSV로 저장.

사용:
  1) 네이버 개발자센터에서 '검색' API 등록 → Client ID/Secret 발급
  2) .env 파일에 키 입력 (.env.example 참고)
  3) keywords.txt 에 수집할 검색어를 한 줄에 하나씩
  4) 실행:
       python run.py                          # keywords.txt 전체, output/ 에 xlsx 저장
       python run.py --keywords 신라면 진라면   # 검색어 직접 지정
       python run.py --format csv --max 300    # csv, 검색어당 최대 300건
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

from collector.sites import navershop
from collector.clean import clean_rows, dedup, key_of
from collector.snowball import candidate_brands
from collector import export

ROOT = Path(__file__).resolve().parent
DEFAULT_KEYWORDS_FILE = ROOT / "keywords.txt"
DEFAULT_OUT_DIR = ROOT / "output"


def load_dotenv(path: Path) -> None:
    """의존성 없이 .env 를 환경변수로 읽는다 (이미 설정된 값은 덮지 않음)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def read_keywords(args) -> list[str]:
    if args.keywords:
        return args.keywords
    path = Path(args.keywords_file)
    if not path.exists():
        sys.exit(f"검색어 파일이 없습니다: {path}  (--keywords 로 직접 줄 수도 있어요)")
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.append(line)
    if not out:
        sys.exit(f"검색어 파일이 비어 있습니다: {path}")
    return out


def run_searches(keywords, client_id, client_secret, args, searched, label=""):
    """검색어 목록을 돌며 수집·정제한다. searched 에 사용한 검색어를 기록."""
    rows: list[dict] = []
    n = len(keywords)
    for i, kw in enumerate(keywords, 1):
        searched.add(kw)
        try:
            r = navershop.search(
                kw, client_id, client_secret,
                max_items=args.max, sort=args.sort, delay=args.delay,
            )
        except Exception as e:  # noqa: BLE001  네트워크/한도 오류는 건너뛰고 계속
            print(f"  [{label}{i}/{n}] {kw}: 실패 — {e}")
            continue
        r = clean_rows(r)  # 브랜드 추출(눈덩이 후보용) + 변형속성 파싱
        rows.extend(r)
        print(f"  [{label}{i}/{n}] {kw}: {len(r)}건")
    return rows


def merge_with_previous(current, prev_path):
    """이전 출력과 병합. 이번에 안 보인 상품은 status=미확인 으로 보존(단종 추적)."""
    prev = export.load(prev_path)
    cur_keys = {key_of(r) for r in current}
    merged = list(current)
    carried = 0
    for r in prev:
        if key_of(r) not in cur_keys:
            r["status"] = "미확인"  # 이번 수집엔 안 보임 → 단종 후보, last_seen 은 그대로
            merged.append(r)
            carried += 1
    return merged, carried


def main() -> None:
    ap = argparse.ArgumentParser(description="네이버쇼핑 브랜드·상품명 수집기")
    ap.add_argument("--keywords", nargs="*", help="검색어 직접 지정 (없으면 keywords.txt 사용)")
    ap.add_argument("--keywords-file", default=str(DEFAULT_KEYWORDS_FILE))
    ap.add_argument("--max", type=int, default=1000, help="검색어당 최대 수집 건수 (최대 1000)")
    ap.add_argument("--sort", default="sim", choices=["sim", "date", "asc", "dsc"])
    ap.add_argument("--delay", type=float, default=0.3, help="페이지 호출 간 지연(초)")
    ap.add_argument("--format", default="xlsx", choices=["xlsx", "csv"])
    ap.add_argument("--out", help="출력 파일 경로 (없으면 output/ 에 자동 생성)")
    ap.add_argument("--snowball", type=int, default=0, metavar="N",
                    help="눈덩이 확장 라운드 수 (수집 결과의 새 브랜드를 검색어로 재투입; 0=끄기)")
    ap.add_argument("--snowball-min", type=int, default=2,
                    help="브랜드 재투입 최소 등장 횟수 (잡음 거르기)")
    ap.add_argument("--snowball-max", type=int, default=50,
                    help="라운드당 재투입할 최대 브랜드 수 (호출량 가드)")
    ap.add_argument("--merge", metavar="PREV",
                    help="이전 출력(csv/xlsx)과 병합해 last_seen·판매상태 갱신")
    args = ap.parse_args()

    load_dotenv(ROOT / ".env")
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 없습니다.\n"
            ".env 파일을 만들거나(예: .env.example) 환경변수로 설정하세요."
        )

    keywords = read_keywords(args)
    print(f"검색어 {len(keywords)}개로 수집 시작 (검색어당 최대 {args.max}건)\n")

    searched: set[str] = set()
    all_rows = run_searches(keywords, client_id, client_secret, args, searched)

    # 눈덩이 확장: 수집된 새 브랜드를 다음 라운드 검색어로 재투입
    for rnd in range(1, args.snowball + 1):
        cands = candidate_brands(all_rows, searched, args.snowball_min, args.snowball_max)
        if not cands:
            print(f"\n눈덩이 {rnd}라운드: 새 브랜드 없음 — 확장 종료")
            break
        preview = ", ".join(cands[:10]) + (" …" if len(cands) > 10 else "")
        print(f"\n눈덩이 {rnd}라운드: 새 브랜드 {len(cands)}개 재투입 → {preview}")
        all_rows += run_searches(cands, client_id, client_secret, args, searched, label=f"R{rnd} ")

    print(f"\n원본 합계 {len(all_rows)}건 → 중복제거 중...")
    all_rows = dedup(all_rows)  # 정제는 run_searches 안에서 이미 끝남
    print(f"중복 제거 후 {len(all_rows)}건")

    if args.merge:
        all_rows, carried = merge_with_previous(all_rows, args.merge)
        print(f"이전 파일 병합: 이번에 안 보인 {carried}건은 판매상태=미확인 으로 보존")

    if not all_rows:
        sys.exit("수집된 상품이 없습니다.")

    if args.out:
        out_path = Path(args.out)
    else:
        DEFAULT_OUT_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = DEFAULT_OUT_DIR / f"products_{stamp}.{args.format}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    export.save(all_rows, str(out_path), args.format)
    print(f"\n저장 완료: {out_path}  ({len(all_rows)}건)")


if __name__ == "__main__":
    main()
