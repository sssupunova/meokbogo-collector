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
  html{{font-size:18px}}
  body{{margin:0;background:var(--bg);color:var(--text);-webkit-font-smoothing:antialiased;
    font-family:'Pretendard','Apple SD Gothic Neo',-apple-system,BlinkMacSystemFont,sans-serif;
    letter-spacing:-0.2px}}
  .topbar{{position:sticky;top:0;z-index:10;background:rgba(255,255,255,.82);
    backdrop-filter:saturate(180%) blur(12px);border-bottom:1px solid var(--line)}}
  .topbar .inner{{max-width:1000px;margin:0 auto;padding:16px 28px;display:flex;align-items:center;gap:12px}}
  .topbar h2{{font-size:20px;font-weight:800;margin:0}}
  .logo{{width:36px;height:36px;border-radius:11px;background:var(--green);color:#fff;
    font-weight:800;font-size:21px;display:flex;align-items:center;justify-content:center}}
  .wrap{{max-width:1000px;margin:0 auto;padding:48px 28px 110px}}
  .hero h1{{font-size:40px;font-weight:800;margin:0 0 14px;letter-spacing:-1.2px;line-height:1.2}}
  .hero p{{font-size:19px;color:var(--sub);margin:0 0 36px;line-height:1.65;max-width:720px}}
  .layout{{display:grid;grid-template-columns:1.55fr 1fr;gap:26px;align-items:start}}
  .card{{background:var(--card);border-radius:26px;padding:38px 40px;
    box-shadow:0 1px 2px rgba(0,0,0,.04),0 14px 36px rgba(20,30,55,.07)}}
  .field{{margin-bottom:28px}} .field:last-of-type{{margin-bottom:10px}}
  .field>label{{display:block;font-size:18px;font-weight:700;margin-bottom:7px}}
  .field>label .opt{{color:var(--sub);font-weight:500;font-size:15px}}
  .hint{{color:var(--sub);font-size:15.5px;margin:0 0 13px;line-height:1.55}}
  select,input,textarea{{width:100%;padding:16px 17px;background:var(--field);border:1.5px solid transparent;
    border-radius:15px;font-size:17px;color:var(--text);font-family:inherit;outline:none;
    transition:border-color .15s,background .15s,box-shadow .15s;-webkit-appearance:none}}
  textarea{{resize:vertical;line-height:1.55}}
  select:focus,input:focus,textarea:focus{{border-color:var(--blue);background:#fff;
    box-shadow:0 0 0 4px rgba(49,130,246,.13)}}
  .grid2{{display:grid;grid-template-columns:1fr 1fr;gap:18px}}
  .seg{{display:flex;background:var(--field);border-radius:15px;padding:5px;gap:5px}}
  .seg button{{flex:1;border:0;background:transparent;padding:14px;border-radius:12px;
    font-size:16.5px;font-weight:700;color:var(--sub);cursor:pointer;transition:.15s}}
  .seg button.on{{background:#fff;color:var(--blue);box-shadow:0 1px 5px rgba(20,30,55,.13)}}
  .submit{{width:100%;padding:19px;background:var(--blue);color:#fff;border:0;border-radius:17px;
    font-size:19px;font-weight:800;cursor:pointer;transition:.15s;margin-top:6px}}
  .submit:hover{{background:var(--blue-d)}} .submit:active{{transform:scale(.99)}}
  .submit:disabled{{background:#c6d6f5;cursor:default}}
  .spin{{display:none;text-align:center;color:var(--blue);font-weight:700;margin-top:20px;font-size:16px}}
  .aside h3{{font-size:19px;font-weight:800;margin:0 0 16px}}
  .aside .item{{margin-bottom:18px}}
  .aside .item b{{display:block;font-size:16.5px;margin-bottom:3px}}
  .aside .item span{{color:var(--sub);font-size:15px;line-height:1.55}}
  .aside .tip{{margin-top:6px;padding:16px;background:#eef4ff;border-radius:14px;
    color:#1b4fb0;font-size:15px;line-height:1.6;font-weight:600}}
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
  @media(max-width:820px){{.layout{{grid-template-columns:1fr}} .hero h1{{font-size:32px}}}}
  @media(max-width:520px){{.grid2{{grid-template-columns:1fr}} .card{{padding:28px 22px}}}}
</style></head><body>
<div class="topbar"><div class="inner"><div class="logo">N</div><h2>네이버쇼핑 수집기</h2></div></div>
<div class="wrap">{body}</div></body></html>""".encode("utf-8")


_PROFILE_DESC = {
    "kfood": "가공식품 (라면·과자·음료 등)",
    "health": "건강기능식품 (홍삼·유산균·비타민 등)",
    "example_cosmetics": "화장품 (예시용 샘플)",
}


def form_body(msg: str = "") -> str:
    opts = ""
    for n in list_profiles():
        desc = _PROFILE_DESC.get(n, "")
        label = f"{n} — {desc}" if desc else n
        opts += f'<option value="{html.escape(n)}">{html.escape(label)}</option>'
    return f"""
<div class="hero">
  <h1>상품 데이터, 버튼 한 번으로.</h1>
  <p>네이버쇼핑에서 <b>브랜드·상품명</b>을 모아 중복을 정리하고 엑셀/CSV로 떨궈주는 도구예요.
  분야를 고르고 시작만 누르면 깔끔한 <b>제품 목록</b>이 만들어집니다.</p>
</div>
{msg}
<div class="layout">
<div class="card">
<form method="post" action="/run" onsubmit="document.getElementById('go').disabled=true;document.getElementById('spin').style.display='block';">

  <div class="field">
    <label>어떤 분야를 모을까요?</label>
    <p class="hint">분야마다 브랜드 목록과 상품명 정리 규칙이 달라요.</p>
    <select name="profile">{opts}</select>
  </div>

  <div class="field">
    <label>수집 방식</label>
    <p class="hint" id="srcHint">준비된 브랜드 목록으로 검색어를 자동으로 만들어 한 번에 모아와요. (추천)</p>
    <div class="seg">
      <button type="button" class="on" data-v="brands" onclick="pick(this)">브랜드 목록 자동</button>
      <button type="button" data-v="keywords" onclick="pick(this)">직접 키워드</button>
    </div>
    <input type="hidden" name="source" id="source" value="brands">
  </div>

  <div class="field" id="kw" style="display:none">
    <label>검색어 직접 입력</label>
    <p class="hint">원하는 검색어를 줄바꿈 또는 쉼표로 구분해 적어요. (예: 농심 라면, 신라면)</p>
    <textarea name="keywords" rows="3" placeholder="농심 라면&#10;오뚜기 라면"></textarea>
  </div>

  <div class="grid2">
    <div class="field">
      <label>검색어당 최대 개수</label>
      <p class="hint">검색어 하나에서 몇 개까지. 많을수록 오래 걸려요. (최대 1000)</p>
      <input name="max" type="number" value="100" min="10" max="1000">
    </div>
    <div class="field">
      <label>검색어 개수 제한 <span class="opt">(선택)</span></label>
      <p class="hint">자동 생성 검색어를 위에서부터 잘라요. 비우면 전부. (테스트 5~10)</p>
      <input name="limit" type="number" min="1" placeholder="전체">
    </div>
  </div>

  <div class="grid2">
    <div class="field">
      <label>눈덩이 확장 <span class="opt">(기본 0)</span></label>
      <p class="hint">새로 발견된 브랜드를 다시 검색어로 넣어 더 넓게. 0=안 함, 1~2면 충분.</p>
      <input name="snowball" type="number" value="0" min="0" max="5">
    </div>
    <div class="field">
      <label>저장 형식</label>
      <p class="hint">CSV는 엑셀·구글시트에서 바로 열려요.</p>
      <select name="format"><option value="csv">CSV (엑셀에서 열림)</option><option value="xlsx">XLSX (엑셀 파일)</option></select>
    </div>
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
  <div class="tip">💡 처음이면 <b>분야</b>만 고르고 <b>검색어 개수 제한 5</b>로 가볍게 한번 돌려보세요.</div>
  <p class="hint" style="margin-top:16px">네이버 API 키(.env)가 설정돼 있어야 동작해요.</p>
</aside>
</div>

<script>
function pick(btn){{
  document.querySelectorAll('.seg button').forEach(b=>b.classList.remove('on'));
  btn.classList.add('on');
  var v=btn.dataset.v; document.getElementById('source').value=v;
  document.getElementById('kw').style.display = v==='keywords' ? 'block':'none';
  document.getElementById('srcHint').textContent = v==='keywords'
    ? '원하는 검색어를 직접 입력해서 모아와요.'
    : '준비된 브랜드 목록으로 검색어를 자동으로 만들어 한 번에 모아와요. (추천)';
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

        argv = [sys.executable, str(ROOT / "run.py"), "--profile", f("profile", "kfood"),
                "--max", f("max", "100"), "--format", f("format", "csv")]
        if f("source") == "keywords":
            kws = [k.strip() for k in re.split(r"[\n,]", f("keywords")) if k.strip()]
            if not kws:
                self._send(page(form_body('<p class="err">키워드를 입력하세요.</p>')))
                return
            argv += ["--keywords"] + kws
        else:
            argv.append("--brands-csv")
            if f("limit"):
                argv += ["--limit", f("limit")]
            if f("snowball") and f("snowball") != "0":
                argv += ["--snowball", f("snowball")]

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
