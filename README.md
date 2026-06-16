# meokbogo-collector

네이버쇼핑에서 **브랜드 · 상품명**을 수집해 엑셀/CSV로 떨구는 독립 크롤링 도구.
[먹보고](https://github.com/sssupunova/meokbogo) 앱과는 분리된 별도 저장소이며, 결과 엑셀을
먹보고 DB의 시드로 활용하는 것이 목적이다. (영양성분·바코드는 먹보고 앱 쪽에서 별도로 채운다.)

## 동작 방식

```
keywords.txt → [네이버쇼핑 검색 API] → 100개씩 페이지네이션 → 브랜드·상품명 정제 → 중복 제거 → output/*.xlsx
```

네이버쇼핑은 공식 검색 API가 있어 HTML 크롤링 없이 JSON으로 상품을 받아온다(합법·안정).
검색어당 최대 1,000건(100 × 10페이지), 하루 25,000건 호출 제한.

## 설치

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

## 설정

1. [네이버 개발자센터](https://developers.naver.com)에서 애플리케이션 등록 → **검색 API** 추가
2. 발급된 Client ID / Secret 을 `.env` 에 입력

```bash
cp .env.example .env
# .env 를 열어 NAVER_CLIENT_ID / NAVER_CLIENT_SECRET 채우기
```

3. `keywords.txt` 에 수집할 검색어를 한 줄에 하나씩. 제품명이 아니라 **형태/카테고리 단위**(`봉지라면`, `과자`, `탄산음료` …)로 넣어, 각 범주의 상위 인기 제품을 모은다.

## 실행

```bash
python run.py                          # keywords.txt 전체 → output/products_*.xlsx
python run.py --keywords 신라면 진라면   # 검색어 직접 지정
python run.py --format csv --max 300    # CSV로, 검색어당 최대 300건
python run.py --sort date               # 정렬: sim(유사도)|date|asc|dsc
```

## 출력 컬럼

`브랜드 | 상품명 | 용량/중량 | 형태 | 입수 | 한정 | 가격 | 판매처 | 카테고리 | 이미지 | 링크 | 상품ID | 판매상태 | 출처 | 검색어 | 수집일시 | 최종확인`

- **용량/중량·형태·입수·한정**: 상품명에서 규칙 기반으로 뽑은 변형속성 (`collector/variants.py`). 예: `농심 신라면 컵 65g 6개입` → 용량 `65g`, 형태 `컵`, 입수 `6개입`.
- **판매상태·최종확인(last_seen)**: 검색에 떴다는 건 그 시점에 시판 중이라는 뜻. 수집을 반복하면 `최종확인`으로 단종 여부를 추적할 수 있다(먹보고 앱 쪽에서 활용).

## 구조

```
collector/
  sites/navershop.py   마켓 어댑터 (1마켓 1파일 — 쿠팡 등 추가 시 여기에)
  clean.py             상품명 태그 제거 · 브랜드 보정 · 변형속성 추출 · 중복 제거
  variants.py          상품명 → 용량/중량 · 형태 · 입수 · 한정 파싱
  export.py            xlsx / csv 저장
run.py                 진입점 (검색어 루프 → 정제 → 저장)
keywords.txt           수집할 검색어 목록 (형태/카테고리 단위 — 봉지라면, 과자 …)
```

## 마켓 추가하기

`collector/sites/` 에 `search(keyword, ...) -> list[dict]` 시그니처를 따르는 모듈을 추가하면
`run.py` 에서 동일하게 호출할 수 있다. 행 스키마는 `collector/export.py` 의 `COLUMNS` 참고.

> 주의: 쿠팡 등은 공개 API가 없고 안티봇(Akamai)이 강해 Selenium/Playwright 가 필요하며
> 차단·유지보수 부담이 크다. 수집 시 각 사이트의 robots.txt / 이용약관을 확인할 것.
