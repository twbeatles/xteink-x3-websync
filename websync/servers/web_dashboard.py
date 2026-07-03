"""X3 WebSync 경량 웹 대시보드 서버"""
import os
import json
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable

_sync_callback: Optional[Callable] = None
_get_log_callback: Optional[Callable] = None
_api_token: str = ""
_pipeline_busy_callback: Optional[Callable[[], bool]] = None


def _html_template(api_token: str) -> str:
    token_js = json.dumps(api_token)
    return f"""
<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>X3 WebSync 대시보드</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: 'Segoe UI', sans-serif; background: #1e1e2e; color: #cdd6f4; padding: 24px; }}
  h1 {{ color: #89b4fa; font-size: 1.6rem; margin-bottom: 20px; }}
  .card {{ background: #313244; border-radius: 12px; padding: 20px; margin-bottom: 16px; }}
  .card h2 {{ color: #89b4fa; font-size: 1rem; margin-bottom: 12px; }}
  button {{ background: #89b4fa; color: #1e1e2e; border: none; border-radius: 8px; padding: 10px 22px; font-size: 0.95rem; cursor: pointer; font-weight: bold; }}
  button:hover {{ background: #b4d0fb; }}
  #log-area {{ background: #181825; border-radius: 8px; padding: 14px; font-family: Consolas, monospace; font-size: 0.82rem; height: 220px; overflow-y: auto; white-space: pre-wrap; color: #a6e3a1; margin-top: 10px; }}
  #sync-result {{ margin-top: 12px; color: #a6e3a1; min-height: 24px; }}
</style>
</head>
<body>
<h1>🚀 X3 WebSync 대시보드</h1>
<div class="card">
  <h2>동기화 제어</h2>
  <button onclick="runSync()">🚀 즉시 동기화 실행</button>
  <div id="sync-result"></div>
</div>
<div class="card">
  <h2>실행 로그</h2>
  <button onclick="refreshLog()">🔄 로그 새로고침</button>
  <div id="log-area">로그를 로드하는 중...</div>
</div>
<script>
const API_TOKEN = {token_js};
function authHeaders() {{
  return API_TOKEN ? {{'Authorization': 'Bearer ' + API_TOKEN}} : {{}};
}}
async function runSync() {{
  document.getElementById('sync-result').textContent = '⏳ 동기화 실행 중...';
  try {{
    const r = await fetch('/api/sync', {{method: 'POST', headers: authHeaders()}});
    const d = await r.json();
    document.getElementById('sync-result').textContent = d.message || d.error || '완료';
  }} catch(e) {{ document.getElementById('sync-result').textContent = '❌ 오류: ' + e; }}
}}
async function refreshLog() {{
  try {{
    const r = await fetch('/api/log', {{headers: authHeaders()}});
    const d = await r.json();
    document.getElementById('log-area').textContent = d.log || '(로그 없음)';
    document.getElementById('log-area').scrollTop = document.getElementById('log-area').scrollHeight;
  }} catch(e) {{ document.getElementById('log-area').textContent = '로그 로드 실패'; }}
}}
refreshLog();
</script>
</body>
</html>
"""


class DashboardHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _check_auth(self) -> bool:
        if not _api_token:
            return True
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {_api_token}":
            return True
        self.send_error(401, "Unauthorized")
        return False

    def do_GET(self):
        if self.path in ("/", "/dashboard"):
            body = _html_template(_api_token).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif self.path == "/api/log":
            if not self._check_auth():
                return
            log_text = ""
            if _get_log_callback:
                log_text = _get_log_callback() or ""
            else:
                from websync.core.paths import PROJECT_ROOT
                log_dir = os.path.join(PROJECT_ROOT, "logs")
                if os.path.isdir(log_dir):
                    files = sorted(os.listdir(log_dir), reverse=True)
                    if files:
                        try:
                            with open(os.path.join(log_dir, files[0]), "r", encoding="utf-8") as f:
                                lines = f.readlines()
                                log_text = "".join(lines[-100:])
                        except Exception:
                            pass
            body = json.dumps({"log": log_text}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/sync":
            if not self._check_auth():
                return
            if _pipeline_busy_callback and _pipeline_busy_callback():
                body = json.dumps({"message": "⚠️ 동기화가 이미 실행 중입니다."}, ensure_ascii=False).encode("utf-8")
            else:
                msg = "동기화가 백그라운드에서 시작됩니다."
                if _sync_callback:
                    threading.Thread(target=_sync_callback, daemon=True).start()
                body = json.dumps({"message": f"✅ {msg}"}, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)


class WebDashboard:
    """웹 대시보드 서버 관리 클래스"""

    def __init__(
        self,
        port: int = 8766,
        bind_host: str = "127.0.0.1",
        api_token: str = "",
        sync_callback: Optional[Callable] = None,
        get_log_callback: Optional[Callable] = None,
        pipeline_busy_callback: Optional[Callable[[], bool]] = None,
    ):
        global _sync_callback, _get_log_callback, _api_token, _pipeline_busy_callback
        self.port = port
        self.bind_host = bind_host
        _sync_callback = sync_callback
        _get_log_callback = get_log_callback
        _api_token = api_token or ""
        _pipeline_busy_callback = pipeline_busy_callback
        self._server: Optional[HTTPServer] = None
        self._running = False

    def start(self) -> bool:
        if self._running:
            return True
        try:
            self._server = HTTPServer((self.bind_host, self.port), DashboardHandler)
            t = threading.Thread(target=self._server.serve_forever, daemon=True)
            t.start()
            self._running = True
            return True
        except Exception as e:
            print(f"❌ 웹 대시보드 서버 시작 실패: {e}")
            return False

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def get_url(self) -> str:
        host = "localhost" if self.bind_host in ("127.0.0.1", "localhost") else self.bind_host
        return f"http://{host}:{self.port}/"
