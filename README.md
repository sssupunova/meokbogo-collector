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

## 출력물 (3종)

한 번 실행하면 세 파일이 나온다.

1. **상세 SKU** `products_*.xlsx` — 변형(용량/입수)별 한 행, 전체 컬럼
2. **★최종 DB 시드** `먹보고_최종DB시드_*.xlsx` — 단일 제품만 추린 먹보고 DB용 (폴더에서 바로 눈에 띄게 별도 이름)
3. **복합 상품** `products_*_composite.xlsx` — 세트/모음/도배 상품을 격리(재정제용)

### 상세 SKU 컬럼
```
브랜드 | 제품명 | 묶음 | 원본상품명 | 용량중량 | 형태 | 입수 | 한정 | 가격 | 판매처
| 카테고리 | 인기순위 | 이미지 | 링크 | 상품ID | 출처 | 검색어 | 신규 | 최초수집일 | 최종확인일 | 판매상태 | 수집일시
```

- **브랜드**: 브랜드 타깃 검색 시 검색어의 브랜드를 행에 주입한다. 네이버 API 가 brand
  필드를 비우거나 서브라인(신라면·맵탱)을 넣는 오염을 막는다. 원본은 `출처`가 아닌 maker 로 보존.
- **제품명**: 원본 상품명에서 용량·입수·괄호·마케팅·SEO 잡음어(봉지라면·야식·캠핑…)를
  걷어내고 중복 토큰을 접은 읽기용 이름(브랜드 포함). 예: `오뚜기 진라면 매운맛 봉지라면 야식
  간식 캠핑` → `오뚜기 진라면 매운맛`.
- **복합**: 세트/모음/도배 상품(단일 제품 아님) 표시. 세트마커(`세트`·`N종`·`+`·`모음`)나
  SEO 제거 후에도 토큰이 과하게 많으면 복합으로 보고, `_composite` 시트로 격리한다.
- **변형속성**(용량중량·형태·입수·한정): 상품명 휴리스틱 파싱 (`collector/variants.py`).
- **인기순위**: 검색 결과 내 위치(1=상단). Open API 엔 랭킹순이 없어 `--sort sim` 순서를 캡처.
- **신규 / 최초·최종확인일 / 판매상태**: 아래 '시판여부 추적' 참고.

### 브랜드·제품명 시드 컬럼
```
브랜드 | 제품명 | 카테고리 | 변형수 | 최저가 | 대표이미지 | 대표링크
```
같은 (브랜드, 제품명)의 변형을 한 행으로 모은 것. 복합(세트/모음)은 제외한다. 먹보고 DB 시드로 바로 쓴다.

## 시판여부 추적 (선택적)

`--state <파일.json>` 을 주면 실행 간 상태를 비교해 last_seen·신제품 발견·단종 후보를 잡는다.

```bash
python run.py --brands-csv --state output/state.json
```

- 이전에 본 상품 → `최초수집일` 보존, `최종확인일` 갱신, `판매중`
- 이번에 처음 본 상품 → `신규=Y`
- 예전엔 봤는데 이번 수집에 없는 상품 → `판매상태=미확인`(단종/판매중단 후보)으로 재출력

상태파일이 없으면 각 행은 이번 수집 기준값만 갖는다(모두 `판매중`).

## 중복 처리 (변형 단위)

네이버쇼핑은 같은 상품을 판매처마다 다른 `product_id` 로 올린다. 그래서 시드 DB 에는
**변형(브랜드 + 제품명 + 용량 + 입수) 하나당 한 행**만 남긴다 (`collector/dedup.py`).

- 판매처·가격·마케팅 문구(무료배송/정품/[행사]…)만 다른 중복은 합친다.
- 용량·입수가 다르면 별개 변형으로 유지한다 (변형속성 보존).
- 합칠 때 **인기순위가 가장 앞선 행**을 대표로 남기고, 빈 필드는 버려지는 중복에서
  메우며(백필), 가격은 **최저가**로 채운다.
- `variant_key` 는 dedup 과 `--state` 추적이 공유한다 → 판매처가 바뀌어 product_id 가
  달라져도 같은 변형이면 동일 식별자라, 실행 간 신규/미확인 판정이 흔들리지 않는다.

## 눈덩이(snowball) 확장

브랜드는 식약처와 독립된 축이라, 수집 결과에서 **시드에 없던 새 브랜드**가 나오면
검색어로 재투입해 커버리지를 넓힐 수 있다.

```bash
python run.py --brands-csv --snowball 2          # 2회차까지 새 브랜드 재투입
python run.py --brands-csv --snowball 2 --snowball-min 5 --snowball-max 30
```

| 옵션 | 기본값 | 설명 |
|---|---|---|
| `--snowball N` | `0`(off) | 확장 회차 수 |
| `--snowball-min` | `3` | 새 브랜드 채택 최소 등장 횟수(잡음 컷) |
| `--snowball-max` | `50` | 회차당 새 브랜드 상한(호출 예산) |

각 회차는 직전 결과에서 시드·기존에 없는 브랜드를 빈도순으로 추려 `brand_only`
검색어로 재투입한다. 새 브랜드가 안 나오면 조기 종료하며, 같은 검색어는 재실행하지 않는다.

## 구조

```
collector/
  sites/navershop.py   마켓 어댑터 (1마켓 1파일 — 쿠팡 등 추가 시 여기에) · 인기순위 캡처
  keywords_gen.py      브랜드 CSV → '브랜드+카테고리' 검색어 자동생성 (눈덩이 확장 공유)
  variants.py          상품명 → 변형속성(용량/형태/입수/한정) 휴리스틱 파싱
  dedup.py             변형(SKU) 단위 중복 제거 · distill(제품 단위 시드) · variant_key
  state.py             실행 간 시판여부 추적 (선택적, --state)
  clean.py             상품명 태그 제거 · 브랜드 보정 · 제품명 정제 · 번들 검출 · 변형속성 파싱
  export.py            xlsx / csv 저장 (상세 SKU + 브랜드·제품명 시드)
run.py                 진입점 (검색어 결정 → 루프 → 정제 → 저장)
keywords.txt           수집할 검색어 목록 (직접 지정용)
data/kr_food_brands_db.csv   브랜드 시드 DB (검색어 자동생성 입력)
```

## 마켓 추가하기

`collector/sites/` 에 `search(keyword, ...) -> list[dict]` 시그니처를 따르는 모듈을 추가하면
`run.py` 에서 동일하게 호출할 수 있다. 행 스키마는 `collector/export.py` 의 `COLUMNS` 참고.

> 주의: 쿠팡 등은 공개 API가 없고 안티봇(Akamai)이 강해 Selenium/Playwright 가 필요하며
> 차단·유지보수 부담이 크다. 수집 시 각 사이트의 robots.txt / 이용약관을 확인할 것.
