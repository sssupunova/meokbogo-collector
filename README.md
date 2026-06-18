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

3. `keywords.txt` 에 수집할 검색어를 한 줄에 하나씩 (또는 아래 '브랜드 기반 검색어 자동생성' 사용)

## 실행

```bash
python run.py                          # keywords.txt 전체 → output/products_*.xlsx
python run.py --keywords 신라면 진라면   # 검색어 직접 지정
python run.py --format csv --max 300    # CSV로, 검색어당 최대 300건
python run.py --sort date               # 정렬: sim(유사도)|date|asc|dsc
```

## 브랜드 기반 검색어 자동생성 (권장)

### 왜 '브랜드 + 카테고리' 인가
이 수집기는 **주요 제품 커버가 안 되는 식약처 DB를 보완**하려는 것이다. 그래서
검색어를 **제품명**으로 시딩하면 순환논리가 된다 — 식약처가 빠뜨린 제품은 제품명
목록에도 없기 때문이다. 대신 검색 단위를 **'브랜드 + 카테고리'** 로 올린다. 브랜드는
유한하고 식약처와 독립된 축이라, `"농심 라면"` 으로 인기순 검색하면 그 브랜드의 실제
주력 제품(식약처가 빠뜨린 것 포함)이 나온다.

### 사용
`data/kr_food_brands_db.csv`(브랜드 시드) 를 읽어 검색어를 자동 생성한다.

```bash
python run.py --brands-csv                       # CSV → '브랜드+카테고리' 검색어 자동생성 후 수집
python run.py --brands-csv --gen-mode brand_only # "농심" 처럼 브랜드만 (호출 적고 넓게)
python run.py --brands-csv --type all            # 가공식품 + 프랜차이즈 (기본은 manufacturer)
python run.py --brands-csv --limit 30            # 상위 30개 검색어만 (CSV 순서 = 매출·순위)
python run.py --brands-csv --dump-keywords keywords.txt  # 생성만 (검수용, 수집·API키 불필요)
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--gen-mode` | `brand_x_category` | `brand_x_category`("농심 라면") / `brand_only`("농심") |
| `--type` | `manufacturer` | `manufacturer`(가공식품) / `franchise` / `all` |
| `--limit` | 없음 | 생성 검색어 상한 (호출 예산 관리) |

> CSV 의 `subcategory` 를 카테고리 축으로 쓰므로 "농심 김치" 같은 헛검색이 생기지 않는다
> (브랜드 × 자기 카테고리만 곱함). manufacturer 의 `brand_name` 은 사실 제품명이라
> 검색어로 쓰지 않고, 검색축은 회사명(`company_name`)을 쓴다.

## 출력 컬럼

```
브랜드 | 상품명 | 용량중량 | 형태 | 입수 | 한정 | 가격 | 판매처 | 카테고리 | 인기순위
| 이미지 | 링크 | 상품ID | 출처 | 검색어 | 신규 | 최초수집일 | 최종확인일 | 판매상태 | 수집일시
```

- **변형속성**(용량중량·형태·입수·한정): 상품명에서 휴리스틱 파싱 (`collector/variants.py`).
  형태 = 봉지/컵/캔/병/팩/박스/스틱/포/통, 입수 = 묶음 개수, 한정 = 한정/에디션/콜라보 등.
- **인기순위**: 검색 결과 내 위치(1=상단). 네이버 Open API 엔 '랭킹순' 정렬이 없어
  `--sort sim`(관련도) 결과의 순서를 인기신호로 캡처한 값이다.
- **신규 / 최초·최종확인일 / 판매상태**: 아래 '시판여부 추적' 참고.

## 시판여부 추적 (선택적)

`--state <파일.json>` 을 주면 실행 간 상태를 비교해 last_seen·신제품 발견·단종 후보를 잡는다.

```bash
python run.py --brands-csv --state output/state.json
```

- 이전에 본 상품 → `최초수집일` 보존, `최종확인일` 갱신, `판매중`
- 이번에 처음 본 상품 → `신규=Y`
- 예전엔 봤는데 이번 수집에 없는 상품 → `판매상태=미확인`(단종/판매중단 후보)으로 재출력

상태파일이 없으면 각 행은 이번 수집 기준값만 갖는다(모두 `판매중`).

## 구조

```
collector/
  sites/navershop.py   마켓 어댑터 (1마켓 1파일 — 쿠팡 등 추가 시 여기에) · 인기순위 캡처
  keywords_gen.py      브랜드 CSV → '브랜드+카테고리' 검색어 자동생성 (눈덩이 확장 공유)
  variants.py          상품명 → 변형속성(용량/형태/입수/한정) 휴리스틱 파싱
  state.py             실행 간 시판여부 추적 (선택적, --state)
  clean.py             상품명 태그 제거 · 브랜드 보정 · 변형속성 파싱 · 중복 제거
  export.py            xlsx / csv 저장
run.py                 진입점 (검색어 결정 → 루프 → 정제 → 저장)
keywords.txt           수집할 검색어 목록 (직접 지정용)
data/kr_food_brands_db.csv   브랜드 시드 DB (검색어 자동생성 입력)
```

## 마켓 추가하기

`collector/sites/` 에 `search(keyword, ...) -> list[dict]` 시그니처를 따르는 모듈을 추가하면
`run.py` 에서 동일하게 호출할 수 있다. 행 스키마는 `collector/export.py` 의 `COLUMNS` 참고.

> 주의: 쿠팡 등은 공개 API가 없고 안티봇(Akamai)이 강해 Selenium/Playwright 가 필요하며
> 차단·유지보수 부담이 크다. 수집 시 각 사이트의 robots.txt / 이용약관을 확인할 것.
