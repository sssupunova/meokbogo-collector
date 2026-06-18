#!/usr/bin/env python3
"""
먹보고 수집기 — 로컬호스트 웹 GUI (추가 의존성 없이 표준 라이브러리만 사용).

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
<title>먹보고 수집기</title>
<style>
  body{{font-family:-apple-system,BlinkMacSystemFont,'Apple SD Gothic Neo',sans-serif;
    max-width:720px;margin:40px auto;padding:0 20px;color:#222;line-height:1.5}}
  h1{{font-size:22px}} label{{display:block;margin:14px 0 4px;font-weight:600}}
  select,input,textarea{{width:100%;padding:8px;border:1px solid #ccc;border-radius:6px;
    font-size:14px;box-sizing:border-box}}
  .row{{display:flex;gap:12px}} .row>div{{flex:1}}
  button{{margin-top:20px;padding:12px 20px;background:#2d6cdf;color:#fff;border:0;
    border-radius:8px;font-size:15px;font-weight:600;cursor:pointer}}
  button:disabled{{background:#9bb6e8}}
  .card{{background:#f7f8fa;border:1px solid #e4e6eb;border-radius:10px;padding:16px;margin:16px 0}}
  .files a{{display:inline-block;margin:6px 10px 6px 0;padding:8px 12px;background:#eaf1ff;
    border-radius:6px;text-decoration:none;color:#1a4fb0;font-weight:600}}
  .seed a{{background:#1a4fb0;color:#fff}}
  pre{{background:#1e1e1e;color:#d4d4d4;padding:14px;border-radius:8px;overflow:auto;font-size:12px;max-height:320px}}
  .muted{{color:#888;font-size:13px}} .err{{color:#c0392b}}
  #spin{{display:none;margin-top:16px;color:#2d6cdf;font-weight:600}}
</style></head><body>{body}</body></html>""".encode("utf-8")


def form_body(msg: str = "") -> str:
    opts = "".join(
        f'<option value="{html.escape(n)}">{html.escape(n)}</option>' for n in list_profiles()
    )
    return f"""
<h1>🍱 먹보고 수집기</h1>
<p class="muted">프로파일을 고르고 수집을 돌리면 <b>상세·시드·복합</b> 파일이 생성됩니다.
(.env 에 네이버 API 키가 있어야 합니다.)</p>
{msg}
<form method="post" action="/run" onsubmit="document.getElementById('go').disabled=true;document.getElementById('spin').style.display='block';">
  <label>도메인 프로파일</label>
  <select name="profile">{opts}</select>

  <label>수집 방식</label>
  <select name="source" onchange="document.getElementById('kw').style.display=this.value==='keywords'?'block':'none';">
    <option value="brands">브랜드 CSV 자동생성 (프로파일의 brands_csv)</option>
    <option value="keywords">직접 키워드 입력</option>
  </select>

  <div id="kw" style="display:none">
    <label>키워드 (줄바꿈 또는 쉼표로 구분)</label>
    <textarea name="keywords" rows="3" placeholder="농심 라면&#10;오뚜기 라면"></textarea>
  </div>

  <div class="row">
    <div><label>검색어당 최대 건수</label><input name="max" type="number" value="100" min="10" max="1000"></div>
    <div><label>검색어 상한(limit, 선택)</label><input name="limit" type="number" min="1" placeholder="전체"></div>
  </div>
  <div class="row">
    <div><label>눈덩이 확장(회차)</label><input name="snowball" type="number" value="0" min="0" max="5"></div>
    <div><label>형식</label><select name="format"><option value="csv">csv</option><option value="xlsx">xlsx</option></select></div>
  </div>

  <button id="go" type="submit">수집 시작</button>
  <div id="spin">⏳ 수집 중… 검색어 수에 따라 수십 초~몇 분 걸릴 수 있어요.</div>
</form>
"""


def result_body(returncode: int, log: str, files: list[tuple[str, str, str]]) -> str:
    links = ""
    for label, name, count in files:
        cls = "seed" if "시드" in label else ""
        q = urllib.parse.quote(name)
        links += f'<span class="{cls}"><a href="/download?f={q}">⬇ {html.escape(label)} ({html.escape(count)})</a></span>'
    status = '<b style="color:#1a7f37">✅ 완료</b>' if returncode == 0 else '<b class="err">⚠ 오류 (로그 확인)</b>'
    files_html = f'<div class="card files">{links}</div>' if files else ""
    return f"""
<h1>🍱 수집 결과 {status}</h1>
{files_html}
<details open><summary>실행 로그</summary><pre>{html.escape(log)}</pre></details>
<p><a href="/">← 다시 수집</a></p>
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
    print(f"먹보고 수집기 웹 GUI → http://localhost:{port}  (Ctrl+C 로 종료)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료")


if __name__ == "__main__":
    main()
