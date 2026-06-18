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
       python run.py --brands-csv             # data/kr_food_brands_db.csv → '브랜드+카테고리' 검색어 자동생성
       python run.py --brands-csv --dump-keywords keywords.txt   # 생성만 (검수용, 수집 안 함)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from collector.sites import navershop
from collector.clean import clean_rows
from collector.dedup import dedup
from collector.export import save
from collector import keywords_gen
from collector import state as state_mod

ROOT = Path(__file__).resolve().parent
DEFAULT_KEYWORDS_FILE = ROOT / "keywords.txt"
DEFAULT_BRANDS_CSV = ROOT / "data" / "kr_food_brands_db.csv"
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


def _read_keywords_file(path: Path) -> list[str]:
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


def build_keywords(args) -> list[str]:
    """검색어 입력원 결정 — 우선순위: --keywords > --brands-csv > keywords.txt."""
    if args.keywords:
        return args.keywords

    if args.brands_csv:
        try:
            brands = keywords_gen.load_brands(args.brands_csv, type_filter=args.type)
        except (FileNotFoundError, ValueError) as e:
            sys.exit(str(e))
        keywords = keywords_gen.generate_keywords(
            brands, mode=args.gen_mode, limit=args.limit,
        )
        if not keywords:
            sys.exit(f"브랜드 CSV 에서 생성된 검색어가 없습니다: {args.brands_csv}")
        calls = keywords_gen.estimate_calls(len(keywords), args.max)
        print(
            f"브랜드 CSV → 검색어 {len(keywords)}개 생성 "
            f"(type={args.type}, mode={args.gen_mode}"
            f"{f', limit={args.limit}' if args.limit else ''})\n"
            f"예상 API 호출 ~{calls}회 (하루 한도 25,000)\n"
        )
        return keywords

    return _read_keywords_file(Path(args.keywords_file))


def main() -> None:
    ap = argparse.ArgumentParser(description="네이버쇼핑 브랜드·상품명 수집기")
    ap.add_argument("--keywords", nargs="*", help="검색어 직접 지정 (없으면 keywords.txt 사용)")
    ap.add_argument("--keywords-file", default=str(DEFAULT_KEYWORDS_FILE))
    # 브랜드 CSV → '브랜드 + 카테고리' 검색어 자동생성
    ap.add_argument(
        "--brands-csv", nargs="?", const=str(DEFAULT_BRANDS_CSV), default=None,
        help="브랜드 CSV 로 검색어 자동생성 (경로 생략 시 data/kr_food_brands_db.csv)",
    )
    ap.add_argument(
        "--type", default="manufacturer", choices=keywords_gen.TYPE_FILTERS,
        help="브랜드 CSV 선별 (기본 manufacturer=가공식품)",
    )
    ap.add_argument(
        "--gen-mode", default="brand_x_category", choices=keywords_gen.GEN_MODES,
        help="검색어 생성 방식 (기본 brand_x_category='농심 라면')",
    )
    ap.add_argument("--limit", type=int, default=None, help="생성 검색어 상한 (CSV 순서대로 자름)")
    ap.add_argument(
        "--dump-keywords", help="생성한 검색어를 파일로만 저장하고 종료 (수집·API키 불필요)",
    )
    ap.add_argument("--max", type=int, default=1000, help="검색어당 최대 수집 건수 (최대 1000)")
    ap.add_argument(
        "--sort", default="sim", choices=["sim", "date", "asc", "dsc"],
        help="정렬(=인기신호 근사). Open API엔 랭킹순이 없어 sim(관련도) 권장, 순서는 인기순위로 캡처",
    )
    ap.add_argument(
        "--state", help="시판여부 추적 상태파일(JSON). 실행 간 first/last_seen·신규·미확인 비교",
    )
    # 눈덩이(snowball) 확장: 수집 결과의 새 브랜드를 검색어로 재투입
    ap.add_argument("--snowball", type=int, default=0, metavar="N", help="눈덩이 확장 회차(0=off)")
    ap.add_argument("--snowball-min", type=int, default=3, help="새 브랜드 채택 최소 등장 횟수")
    ap.add_argument("--snowball-max", type=int, default=50, help="회차당 새 브랜드 상한")
    ap.add_argument("--delay", type=float, default=0.3, help="페이지 호출 간 지연(초)")
    ap.add_argument("--format", default="xlsx", choices=["xlsx", "csv"])
    ap.add_argument("--out", help="출력 파일 경로 (없으면 output/ 에 자동 생성)")
    args = ap.parse_args()

    keywords = build_keywords(args)

    # 검색어 생성만 하고 끝내는 모드 (검수용) — 수집 안 하므로 API 키 불필요
    if args.dump_keywords:
        out = Path(args.dump_keywords)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(keywords) + "\n", encoding="utf-8")
        print(f"검색어 {len(keywords)}개 저장: {out}")
        return

    load_dotenv(ROOT / ".env")
    client_id = os.environ.get("NAVER_CLIENT_ID")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET")
    if not client_id or not client_secret:
        sys.exit(
            "NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 가 없습니다.\n"
            ".env 파일을 만들거나(예: .env.example) 환경변수로 설정하세요."
        )

    print(f"검색어 {len(keywords)}개로 수집 시작 (검색어당 최대 {args.max}건)\n")

    searched: set[str] = set()

    def collect(kw_list: list[str]) -> list[dict]:
        """검색어 리스트를 수집해 정제까지 마친 행 리스트를 돌려준다(이미 검색한 건 건너뜀)."""
        rows: list[dict] = []
        todo = [k for k in kw_list if k not in searched]
        for i, kw in enumerate(todo, 1):
            searched.add(kw)
            try:
                r = navershop.search(
                    kw, client_id, client_secret,
                    max_items=args.max, sort=args.sort, delay=args.delay,
                )
            except Exception as e:  # noqa: BLE001  네트워크/한도 오류는 건너뛰고 계속
                print(f"  [{i}/{len(todo)}] {kw}: 실패 — {e}")
                continue
            rows.extend(r)
            print(f"  [{i}/{len(todo)}] {kw}: {len(r)}건")
        return clean_rows(rows)

    all_rows: list[dict] = []
    new_rows = collect(keywords)
    all_rows.extend(new_rows)

    # 눈덩이 확장: 직전 결과의 '새 브랜드'를 brand_only 검색어로 재투입 (반복)
    if args.snowball:
        # 시드 브랜드(이미 검색축으로 쓴 것)는 새 브랜드에서 제외
        known_brands: set[str] = set()
        if args.brands_csv:
            try:
                seeds = keywords_gen.load_brands(args.brands_csv, type_filter=args.type)
                known_brands = {b.search_brand.lower() for b in seeds}
            except (FileNotFoundError, ValueError):
                pass
        for rnd in range(1, args.snowball + 1):
            new_brands = keywords_gen.discover_brands(
                new_rows, known_brands,
                min_count=args.snowball_min, limit=args.snowball_max,
            )
            if not new_brands:
                print(f"눈덩이 {rnd}회차: 새 브랜드 없음 — 종료")
                break
            for b in new_brands:
                known_brands.add(b.lower())
            kw2 = keywords_gen.generate_keywords([], mode="brand_only", extra_brands=new_brands)
            print(f"\n눈덩이 {rnd}/{args.snowball}회차: 새 브랜드 {len(new_brands)}개 재투입")
            new_rows = collect(kw2)
            all_rows.extend(new_rows)

    print(f"\n원본 합계 {len(all_rows)}건 → 변형 단위 중복제거 중...")
    all_rows = dedup(all_rows)
    print(f"중복 제거 후 {len(all_rows)}건")

    if not all_rows:
        sys.exit("수집된 상품이 없습니다.")

    # 실행 간 시판여부 추적 (선택적) — first/last_seen·신규·미확인 갱신
    if args.state:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        prev = state_mod.load_state(args.state)
        all_rows, new_state, st = state_mod.apply_state(all_rows, prev, now)
        state_mod.save_state(args.state, new_state)
        print(
            f"상태 추적: 신규 {st['new']} · 기존 {st['seen']} · 미확인 {st['missing']}"
            f"  → {args.state}"
        )

    if args.out:
        out_path = Path(args.out)
    else:
        DEFAULT_OUT_DIR.mkdir(exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = DEFAULT_OUT_DIR / f"products_{stamp}.{args.format}"

    out_path.parent.mkdir(parents=True, exist_ok=True)
    save(all_rows, str(out_path), args.format)
    print(f"\n저장 완료: {out_path}  ({len(all_rows)}건)")


if __name__ == "__main__":
    main()
