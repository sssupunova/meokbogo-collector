#!/usr/bin/env python3
"""
네이버쇼핑 수집기 — 로컬호스트 웹 GUI (추가 의존성 없이 표준 라이브러리만 사용).

  python web.py            # http://localhost:8000
  python web.py 8080       # 포트 지정

프로파일(kfood/health/…)을 고르고 '브랜드 CSV 자동생성' 또는 '직접 키워드'로
수집을 돌린 뒤, 결과 요약과 출력 파일(상세/시드/복합) 다운로드 링크를 보여준다.
내부적으로는 검증된 run.py 를 그대로 호출한다(서브프로세스).
"""

from __future__ import annotations

import html
import re
import subprocess
import sys
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "output"
PROFILES_DIR = ROOT / "profiles"

_SAVE_RE = re.compile(r"저장 완료\(([^)]+)\):\s*(.+?)\s*\((.+?)\)\s*$")


def list_profiles() -> list[str]:
    names = {"kfood"}  # 빌트인 기본
    if PROFILES_DIR.exists():
        for p in PROFILES_DIR.glob("*.json"):
            names.add(p.stem)
    return sorted(names)


def page(body: str) -> bytes:
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>네이버쇼핑 수집기</title>
<link rel="preconnect" href="https://cdn.jsdelivr.net">
<link rel="stylesheet" href="https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/static/pretendard.min.css">
<style>
  :root{{--blue:#3182f6;--blue-d:#1b64da;--bg:#f2f4f6;--card:#fff;--text:#191f28;
    --sub:#6b7684;--field:#f2f4f6;--line:#e5e8eb;--green:#03c75a}}
  *{{box-sizing:border-box}}
  html{{font-size:20px}}
  body{{margin:0;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;
    font-family:'Pretendard','Apple SD Gothic Neo',-apple-system,BlinkMacSystemFont,sans-serif;
    letter-spacing:-0.2px}}
  .topbar{{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.82);
    backdrop-filter:saturate(180%) blur(12px);border-bottom:1px solid var(--line)}}
  .topbar .inner{{max-width:1240px;margin:0 auto;padding:18px 32px;display:flex;align-items:center;gap:13px}}
  .topbar h2{{font-size:23px;font-weight:800;margin:0}}
  .logo{{width:36px;height:36px;border-radius:11px;background:var(--green);color:#fff;
    font-weight:800;font-size:21px;display:flex;align-items:center;justify-content:center}}
  .wrap{{max-width:1240px;margin:0 auto;padding:52px 32px 120px}}
  .hero h1{{font-size:48px;font-weight:800;margin:0 0 16px;letter-spacing:-1.4px;line-height:1.18}}
  .hero p{{font-size:22px;color:#4e5968;margin:0 0 40px;line-height:1.6;max-width:880px}}
  .layout{{display:grid;grid-template-columns:1.7fr 1fr;gap:32px;align-items:start}}
  .card{{background:var(--card);border-radius:26px;padding:42px 46px;
    box-shadow:0 1px 2px rgba(0,0,0,.04),0 14px 36px rgba(20,30,55,.07)}}
  .field{{margin-bottom:28px}} .field:last-of-type{{margin-bottom:10px}}
  .field>label{{display:block;font-size:21px;font-weight:800;margin-bottom:8px}}
  .field>label .opt{{color:#6b7684;font-weight:500;font-size:16px}}
  .hint{{color:#4e5968;font-size:17px;margin:0 0 14px;line-height:1.6}}
  select,input,textarea{{width:100%;padding:18px 18px;background:var(--field);border:1.5px solid transparent;
    border-radius:15px;font-size:19px;color:var(--text);font-family:inherit;outline:none;
    transition:border-color .15s,background .15s,box-shadow .15s;-webkit-appearance:none}}
  textarea{{resize:vertical;line-height:1.55}}
  select:focus,input:focus,textarea:focus{{border-color:var(--blue);background:#fff;
    box-shadow:0 0 0 4px rgba(49,130,246,.13)}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
  .seg{{display:flex;background:var(--field);border-radius:15px;padding:5px;gap:5px}}
  .seg button{{flex:1;border:0;background:transparent;padding:15px;border-radius:12px;
    font-size:18px;font-weight:700;color:#4e5968;cursor:pointer;transition:.15s}}
  .seg button.on{{background:#fff;color:var(--blue);box-shadow:0 1px 5px rgba(20,30,55,.13)}}
  .submit{{width:100%;padding:21px;background:var(--blue);color:#fff;border:0;border-radius:17px;
    font-size:22px;font-weight:800;cursor:pointer;transition:.15s;margin-top:8px}}
  .submit:hover{{background:var(--blue-d)}} .submit:active{{transform:scale(.99)}}
  .submit:disabled{{background:#c6d6f5;cursor:default}}
  .spin{{display:none;text-align:center;color:var(--blue);font-weight:700;margin-top:20px;font-size:16px}}
  .aside h3{{font-size:22px;font-weight:800;margin:0 0 18px}}
  .aside .item{{margin-bottom:20px}}
  .aside .item b{{display:block;font-size:18.5px;margin-bottom:4px}}
  .aside .item span{{color:#4e5968;font-size:16.5px;line-height:1.6}}
  .aside .tip{{margin-top:6px;padding:18px;background:#eef4ff;border-radius:14px;
    color:#1b4fb0;font-size:16.5px;line-height:1.6;font-weight:600}}
  .chips{{display:flex;flex-wrap:wrap;gap:12px;margin:6px 0}}
  .chips a{{display:flex;flex-direction:column;gap:3px;padding:18px 20px;background:var(--field);
    border-radius:16px;text-decoration:none;color:var(--text);font-weight:700;font-size:17px;
    transition:.15s;flex:1;min-width:180px}}
  .chips a:hover{{background:#e8eef9}}
  .chips a.seed{{background:var(--blue);color:#fff}} .chips a.seed:hover{{background:var(--blue-d)}}
  .chips small{{font-weight:600;opacity:.75;font-size:14px}}
  .status{{font-size:26px;font-weight:800;margin:0 0 6px}}
  details{{margin-top:20px}} summary{{cursor:pointer;color:var(--sub);font-size:15.5px;font-weight:600}}
  pre{{background:#0f1115;color:#cdd3de;padding:18px;border-radius:15px;overflow:auto;
    font-size:13.5px;line-height:1.6;max-height:360px;margin-top:14px}}
  .err{{color:#e0264b}}
  a.back{{display:inline-block;margin-top:24px;color:var(--blue);font-weight:700;
    text-decoration:none;font-size:16.5px}}
  /* 강조 블록: 검색어당 최대개수 (위계 ↑) */
  .prominent{{background:linear-gradient(180deg,#eef4ff,#f6f9ff);border:1.5px solid #d8e6ff;
    border-radius:20px;padding:24px 24px 26px;margin-bottom:28px}}
  .prominent>label{{font-size:24px;font-weight:800;margin-bottom:8px}}
  .rangewrap{{display:flex;align-items:center;gap:18px;margin-top:10px}}
  .rangewrap input[type=range]{{flex:1;-webkit-appearance:none;appearance:none;height:10px;
    border-radius:6px;background:#cfe0ff;padding:0;border:0;outline:none}}
  .rangewrap input[type=range]::-webkit-slider-thumb{{-webkit-appearance:none;appearance:none;
    width:28px;height:28px;border-radius:50%;background:var(--blue);cursor:pointer;
    box-shadow:0 2px 8px rgba(49,130,246,.45)}}
  output#maxv{{min-width:108px;text-align:center;font-size:30px;font-weight:800;color:var(--blue);
    background:#fff;border-radius:13px;padding:11px 0;box-shadow:0 1px 3px rgba(0,0,0,.07)}}
  /* 카테고리 선택 칩 */
  .catgroup{{margin-bottom:4px}}
  .catgroup .gname{{font-size:17px;font-weight:800;color:#3d4651;margin:0 0 10px}}
  .catchips{{display:flex;flex-wrap:wrap;gap:10px}}
  .chk input{{position:absolute;opacity:0;width:0;height:0}}
  .chk span{{display:inline-block;padding:13px 20px;background:var(--field);border-radius:999px;
    font-size:18px;font-weight:700;cursor:pointer;border:2px solid transparent;
    transition:.12s;color:#3d4651}}
  .chk input:checked+span{{background:#e7f0ff;border-color:var(--blue);color:var(--blue-d)}}
  .chk input:focus-visible+span{{box-shadow:0 0 0 4px rgba(49,130,246,.2)}}
  /* 카테고리: 내부 스크롤 없이 2열로 전부 펼침 */
  .catbox{{display:grid;grid-template-columns:1fr 1fr;gap:20px 32px;padding:2px;margin-top:6px}}
  @media(max-width:900px){{.layout{{grid-template-columns:1fr}} .hero h1{{font-size:38px}}}}
  @media(max-width:560px){{.grid2,.catbox{{grid-template-columns:1fr}} .card{{padding:30px 24px}}}}
</style></head><body>
<div class="topbar"><div class="inner"><div class="logo">N</div><h2>네이버쇼핑 수집기</h2></div></div>
<div class="wrap">{body}</div></body></html>""".encode("utf-8")


_PROFILE_DESC = {
    "general": "범용 — 아무 카테고리/키워드나 (브랜드 자동 ✕)",
    "kfood": "가공식품 (라면·과자·음료 등)",
    "health": "건강기능식품 (홍삼·유산균·비타민 등)",
    "example_cosmetics": "화장품 (예시용 샘플)",
}

# 네이버쇼핑 대분류 → 중분류 (카테고리 선택기에서 검색어로 사용)
NAVER_CATEGORIES = {
    "식품": ["라면", "과자", "스낵", "음료", "커피", "생수", "건강식품", "즉석밥", "냉동식품", "소스", "유제품"],
    "화장품/미용": ["스킨케어", "메이크업", "마스크팩", "향수", "헤어케어", "바디케어", "선크림", "네일"],
    "디지털/가전": ["노트북", "휴대폰", "이어폰", "TV", "냉장고", "세탁기", "청소기", "모니터", "키보드"],
    "패션의류": ["여성의류", "남성의류", "아우터", "티셔츠", "원피스", "청바지"],
    "패션잡화": ["운동화", "구두", "가방", "지갑", "모자", "시계", "선글라스"],
    "생활/건강": ["세제", "화장지", "영양제", "칫솔", "주방세제", "마스크", "수건"],
    "출산/육아": ["분유", "기저귀", "물티슈", "유아간식", "아기로션", "젖병"],
    "스포츠/레저": ["등산", "골프", "헬스", "자전거", "캠핑", "요가매트"],
    "가구/인테리어": ["침대", "소파", "책상", "의자", "조명", "수납장"],
    "반려동물": ["강아지사료", "고양이사료", "반려동물간식", "고양이모래", "강아지간식"],
}


def category_picker() -> str:
    blocks = ""
    for group, items in NAVER_CATEGORIES.items():
        chips = "".join(
            f'<label class="chk"><input type="checkbox" name="cat" value="{html.escape(c)}">'
            f'<span>{html.escape(c)}</span></label>'
            for c in items
        )
        blocks += f'<div class="catgroup"><p class="gname">{html.escape(group)}</p><div class="catchips">{chips}</div></div>'
    return f'<div class="catbox">{blocks}</div>'


BRANDSETS = [("kfood", "가공식품 — 라면·과자·음료 등 (약 50개 브랜드)"),
             ("health", "건강기능식품 — 홍삼·유산균·비타민 등 (약 70개 브랜드)")]


def form_body(msg: str = "") -> str:
    bopts = "".join(
        f'<option value="{html.escape(v)}">{html.escape(t)}</option>' for v, t in BRANDSETS
    )
    return f"""
<div class="hero">
  <h1>상품 데이터, 버튼 한 번으로.</h1>
  <p>네이버쇼핑에서 <b>브랜드·상품명</b>을 모아 중복을 정리하고 엑셀/CSV로 떨궈주는 도구예요.
  무엇을 모을지 고르고 시작만 누르면 깔끔한 <b>제품 목록</b>이 만들어집니다.</p>
</div>
{msg}
<div class="layout">
<div class="card">
<form method="post" action="/run" onsubmit="document.getElementById('go').disabled=true;document.getElementById('spin').style.display='block';">

  <div class="field">
    <label>무엇을 모을까요?</label>
    <p class="hint" id="srcHint">네이버쇼핑 카테고리를 골라 그 이름으로 모아와요. (가장 넓게)</p>
    <div class="seg">
      <button type="button" class="on" data-v="category" onclick="pick(this)">카테고리</button>
      <button type="button" data-v="brandset" onclick="pick(this)">준비된 브랜드셋</button>
      <button type="button" data-v="keywords" onclick="pick(this)">직접 키워드</button>
    </div>
    <input type="hidden" name="source" id="source" value="category">
  </div>

  <div class="field" id="catBlock">
    <label>네이버쇼핑 카테고리 고르기</label>
    <p class="hint">고른 카테고리 이름이 그대로 검색어가 돼요. 여러 개 선택 가능(결과의 <b>카테고리</b> 칸으로 구분돼요).</p>
    {category_picker()}
  </div>

  <div class="field" id="bsBlock" style="display:none">
    <label>준비된 브랜드셋</label>
    <p class="hint">미리 정리해 둔 브랜드 목록으로 '브랜드 × 카테고리' 검색어를 자동으로 만들어 한 번에 모아요.
      그 분야에 맞는 상품명 정리 규칙도 자동 적용돼요.</p>
    <select name="brandset" id="brandset">{bopts}</select>
  </div>

  <div class="field" id="kw" style="display:none">
    <label>검색어 직접 입력</label>
    <p class="hint">원하는 검색어를 줄바꿈 또는 쉼표로 구분해 적어요. (예: 농심 라면, 신라면)</p>
    <textarea name="keywords" rows="3" placeholder="농심 라면&#10;오뚜기 라면"></textarea>
  </div>

  <div class="prominent">
    <label>한 검색어에서 몇 개나 모을까요?</label>
    <p class="hint">이게 수집량을 좌우해요. 많을수록 더 많이 모으지만 더 오래 걸립니다. (최대 1,000)</p>
    <div class="rangewrap">
      <input type="range" name="max" min="10" max="1000" step="10" value="100"
             oninput="document.getElementById('maxv').textContent=this.value">
      <output id="maxv">100</output>
    </div>
  </div>

  <div class="field" id="limitField" style="display:none">
    <label>검색어 개수 제한 <span class="opt">(선택 · 테스트용)</span></label>
    <p class="hint">브랜드셋은 브랜드×카테고리로 검색어가 <b>수십~수백 개</b> 만들어져요.
      그게 부담되면 <b>위에서부터 N개</b>만 쓰도록 줄여요. 비우면 전부.
      예: <b>5</b> → 상위 5개 검색어만 돌려 빠르게 미리보기.</p>
    <input name="limit" type="number" min="1" placeholder="전체 (비워두기)">
  </div>

  <div class="field">
    <label>검색어 자동 추가 <span class="opt">(선택 · 회차)</span></label>
    <p class="hint">처음엔 고른 검색어로만 모아요. 그 결과에 <b>처음 검색어엔 없던 새 브랜드</b>가
      보이면, 그 브랜드를 <b>검색어로 추가해 한 번 더</b> 모읍니다. 고른 회차만큼 반복돼
      검색어가 점점 늘어나요. <b>안 함</b>이면 처음 검색어 그대로만.</p>
    <div class="seg" id="snowSeg">
      <button type="button" class="on" data-v="0" onclick="pickSnow(this)">안 함</button>
      <button type="button" data-v="1" onclick="pickSnow(this)">1회 더</button>
      <button type="button" data-v="2" onclick="pickSnow(this)">2회 더</button>
      <button type="button" data-v="3" onclick="pickSnow(this)">3회 더</button>
    </div>
    <input type="hidden" name="snowball" id="snowball" value="0">
  </div>

  <div class="field">
    <label>저장 형식</label>
    <p class="hint">CSV는 엑셀·구글시트에서 바로 열려요. XLSX는 엑셀 파일이에요.</p>
    <select name="format"><option value="csv">CSV (엑셀에서 열림)</option><option value="xlsx">XLSX (엑셀 파일)</option></select>
  </div>

  <button id="go" class="submit" type="submit">수집 시작하기</button>
  <div class="spin" id="spin">⏳ 모으는 중… 검색어 수에 따라 수십 초~몇 분 걸려요.</div>
</form>
</div>

<aside class="card aside">
  <h3>이렇게 나와요</h3>
  <div class="item"><b>① 상세</b><span>용량·가격·판매처까지 전부 담긴 원본 표.</span></div>
  <div class="item"><b>② 제품 시드 ⭐</b><span>중복을 정리한 깔끔한 제품 목록. 최종 DB에 바로 쓰는 파일이에요.</span></div>
  <div class="item"><b>③ 복합</b><span>여러 개 묶음·세트 상품을 따로 빼둔 표(나중에 손볼 용도).</span></div>
  <div class="tip">💡 정리 규칙(분야)은 고른 항목에 맞춰 <b>자동</b>으로 적용돼요. 따로 안 골라도 돼요.</div>
  <p class="hint" style="margin-top:16px">네이버 API 키(.env)가 설정돼 있어야 동작해요.</p>
</aside>
</div>

<script>
function pick(btn){{
  btn.parentNode.querySelectorAll('button').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  var v=btn.dataset.v; document.getElementById('source').value=v;
  document.getElementById('catBlock').style.display   = v==='category' ? 'block':'none';
  document.getElementById('bsBlock').style.display    = v==='brandset' ? 'block':'none';
  document.getElementById('kw').style.display         = v==='keywords' ? 'block':'none';
  document.getElementById('limitField').style.display = v==='brandset' ? 'block':'none';
  var hints={{category:'네이버쇼핑 카테고리를 골라 그 이름으로 모아와요. (가장 넓게)',
    brandset:'미리 정리해 둔 브랜드 목록으로 자동 수집해요. 그 분야 정리 규칙도 자동 적용.',
    keywords:'원하는 검색어를 직접 입력해서 모아와요.'}};
  document.getElementById('srcHint').textContent=hints[v];
}}
function pickSnow(btn){{
  btn.parentNode.querySelectorAll('button').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on'); document.getElementById('snowball').value=btn.dataset.v;
}}
</script>
"""


def result_body(returncode: int, log: str, files: list[tuple[str, str, str]]) -> str:
    chips = ""
    for label, name, count in files:
        cls = "seed" if "시드" in label else ""
        q = urllib.parse.quote(name)
        chips += (f'<a class="{cls}" href="/download?f={q}">⬇ {html.escape(label)}'
                  f'<small>{html.escape(count)}</small></a>')
    ok = returncode == 0
    status = ('<p class="status">✅ 수집 완료</p>' if ok
              else '<p class="status err">⚠ 오류가 났어요</p>')
    chips_html = f'<div class="chips">{chips}</div>' if chips else ""
    hint = ('<p class="hint">아래에서 파일을 내려받으세요. <b>제품 시드</b>가 최종 DB용이에요.</p>'
            if ok else '<p class="hint">아래 로그에서 원인을 확인하세요 (보통 API 키 누락·검색어 없음).</p>')
    return f"""
<div class="hero"><h1>수집 결과</h1></div>
<div class="card">
  {status}
  {hint}
  {chips_html}
  <details {'open' if not ok else ''}><summary>실행 로그 보기</summary><pre>{html.escape(log)}</pre></details>
  <a class="back" href="/">← 다시 수집하기</a>
</div>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, body: bytes, status: int = 200, ctype: str = "text/html; charset=utf-8"):
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/":
            self._send(page(form_body()))
        elif parsed.path == "/download":
            self._download(parsed)
        else:
            self._send(page("<h1>404</h1><p><a href='/'>홈</a></p>"), 404)

    def _download(self, parsed):
        qs = urllib.parse.parse_qs(parsed.query)
        name = (qs.get("f") or [""])[0]
        target = (OUT_DIR / name).resolve()
        # output/ 밖 접근 차단
        if OUT_DIR not in target.parents or not target.is_file():
            self._send(page("<h1>파일 없음</h1>"), 404)
            return
        data = target.read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", "application/octet-stream")
        self.send_header(
            "Content-Disposition",
            "attachment; filename*=UTF-8''" + urllib.parse.quote(target.name),
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_POST(self):
        if urllib.parse.urlparse(self.path).path != "/run":
            self._send(page("<h1>404</h1>"), 404)
            return
        length = int(self.headers.get("Content-Length", 0))
        form = urllib.parse.parse_qs(self.rfile.read(length).decode("utf-8"))

        def f(k, d=""):
            return (form.get(k) or [d])[0].strip()

        src = f("source", "category")
        snow = f("snowball")
        # 정제 규칙(프로파일)은 선택에 따라 자동 결정 — 사용자가 따로 안 고른다.
        profile = f("brandset", "kfood") if src == "brandset" else "general"
        argv = [sys.executable, str(ROOT / "run.py"), "--profile", profile,
                "--max", f("max", "100"), "--format", f("format", "csv")]

        def add_snow():
            if snow and snow != "0":
                argv.extend(["--snowball", snow])

        if src == "brandset":
            argv.append("--brands-csv")
            if f("limit"):
                argv += ["--limit", f("limit")]
            add_snow()
        elif src == "keywords":
            kws = [k.strip() for k in re.split(r"[\n,]", f("keywords")) if k.strip()]
            if not kws:
                self._send(page(form_body('<p class="err">키워드를 입력하세요.</p>')))
                return
            argv += ["--keywords"] + kws
            add_snow()
        else:  # category (기본)
            cats = [c.strip() for c in form.get("cat", []) if c.strip()]
            if not cats:
                self._send(page(form_body('<p class="err">카테고리를 한 개 이상 선택하세요.</p>')))
                return
            argv += ["--keywords"] + cats
            add_snow()

        try:
            proc = subprocess.run(argv, cwd=str(ROOT), capture_output=True, text=True, timeout=1800)
            log = (proc.stdout or "") + (("\n[stderr]\n" + proc.stderr) if proc.stderr else "")
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            log, rc = "시간 초과(30분). 검색어를 줄여보세요.", 1

        files = []
        for line in log.splitlines():
            m = _SAVE_RE.search(line.strip())
            if m:
                files.append((m.group(1), Path(m.group(2)).name, m.group(3)))
        self._send(page(result_body(rc, log, files)))

    def log_message(self, *a):  # 콘솔 접속로그 끔
        pass


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    OUT_DIR.mkdir(exist_ok=True)
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    print(f"네이버쇼핑 수집기 웹 GUI → http://localhost:{port}  (Ctrl+C 로 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
