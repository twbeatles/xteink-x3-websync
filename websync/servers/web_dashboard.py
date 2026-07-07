"""X3 WebSync 경량 웹 대시보드 서버"""
import os
import json
import hmac
import hashlib
import threading
import http.cookies
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable

_session_cookie_name = "x3sync_session"


def _session_value(api_token: str) -> str:
    return hmac.new(api_token.encode("utf-8"), b"x3websync-session-v1", hashlib.sha256).hexdigest()


def _login_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>X3 WebSync 로그인</title>
<style>
  body { font-family: 'Segoe UI', sans-serif; background: #1e1e2e; color: #cdd6f4; display:flex; align-items:center; justify-content:center; min-height:100vh; margin:0; }
  .card { background:#313244; padding:28px; border-radius:12px; width:min(400px, 90vw); }
  h1 { color:#89b4fa; font-size:1.2rem; margin-bottom:16px; }
  input { width:100%; padding:10px; border-radius:8px; border:1px solid #45475a; background:#181825; color:#cdd6f4; margin:8px 0 16px; }
  button { width:100%; background:#89b4fa; color:#1e1e2e; border:none; border-radius:8px; padding:10px; font-weight:bold; cursor:pointer; }
  #msg { color:#f38ba8; min-height:20px; font-size:0.9rem; }
  p { font-size:0.85rem; color:#a6adc8; }
</style>
</head>
<body>
<div class="card">
  <h1>🔐 X3 WebSync 대시보드</h1>
  <p>config.json의 <code>web_dashboard.api_token</code> 값을 입력하세요.</p>
  <input id="token" type="password" placeholder="API 토큰" autocomplete="current-password">
  <button onclick="login()">로그인</button>
  <div id="msg"></div>
</div>
<script>
async function login() {
  const token = document.getElementById('token').value.trim();
  if (!token) { document.getElementById('msg').textContent = '토큰을 입력하세요.'; return; }
  try {
    const r = await fetch('/api/login', {
      method: 'POST',
      headers: {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token},
      body: JSON.stringify({token})
    });
    const d = await r.json();
    if (r.ok) { window.location.href = '/dashboard'; }
    else { document.getElementById('msg').textContent = d.error || '로그인 실패'; }
  } catch(e) { document.getElementById('msg').textContent = '오류: ' + e; }
}
</script>
</body>
</html>"""


def _dashboard_html() -> str:
    return """<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>X3 WebSync 대시보드</title>
<style>
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'Segoe UI', sans-serif; background: #1e1e2e; color: #cdd6f4; padding: 24px; }
  h1 { color: #89b4fa; font-size: 1.6rem; margin-bottom: 20px; }
  .card { background: #313244; border-radius: 12px; padding: 20px; margin-bottom: 16px; }
  .card h2 { color: #89b4fa; font-size: 1rem; margin-bottom: 12px; }
  button { background: #89b4fa; color: #1e1e2e; border: none; border-radius: 8px; padding: 10px 22px; font-size: 0.95rem; cursor: pointer; font-weight: bold; margin-right:8px; }
  button:hover { background: #b4d0fb; }
  #log-area { background: #181825; border-radius: 8px; padding: 14px; font-family: Consolas, monospace; font-size: 0.82rem; height: 220px; overflow-y: auto; white-space: pre-wrap; color: #a6e3a1; margin-top: 10px; }
  #sync-result, #status-area { margin-top: 12px; color: #a6e3a1; min-height: 24px; font-size:0.9rem; }
</style>
</head>
<body>
<h1>🚀 X3 WebSync 대시보드</h1>
<div class="card">
  <h2>동기화 제어</h2>
  <button onclick="runSync()">🚀 즉시 동기화 실행</button>
  <button onclick="refreshStatus()">📊 상태 새로고침</button>
  <div id="sync-result"></div>
  <div id="status-area"></div>
</div>
<div class="card">
  <h2>실행 로그</h2>
  <button onclick="refreshLog()">🔄 로그 새로고침</button>
  <div id="log-area">로그를 로드하는 중...</div>
</div>
<script>
async function apiFetch(url, opts={}) {
  const r = await fetch(url, {credentials: 'same-origin', ...opts});
  if (r.status === 401) { window.location.href = '/'; return null; }
  return r;
}
async function runSync() {
  document.getElementById('sync-result').textContent = '⏳ 동기화 실행 중...';
  const r = await apiFetch('/api/sync', {method: 'POST'});
  if (!r) return;
  const d = await r.json();
  document.getElementById('sync-result').textContent = d.message || d.error || '완료';
  refreshStatus();
}
async function refreshStatus() {
  const r = await apiFetch('/api/status');
  if (!r) return;
  const d = await r.json();
  document.getElementById('status-area').textContent = JSON.stringify(d, null, 2);
}
async function refreshLog() {
  const r = await apiFetch('/api/log');
  if (!r) return;
  const d = await r.json();
  document.getElementById('log-area').textContent = d.log || '(로그 없음)';
  document.getElementById('log-area').scrollTop = document.getElementById('log-area').scrollHeight;
}
refreshLog();
refreshStatus();
setInterval(refreshStatus, 5000);
</script>
</body>
</html>"""


class _DashboardHTTPServer(HTTPServer):
    """핸들러에 대시보드 설정·콜백을 주입하는 HTTP 서버"""

    def __init__(
        self,
        server_address,
        api_token: str,
        sync_callback: Optional[Callable],
        get_log_callback: Optional[Callable],
        pipeline_busy_callback: Optional[Callable[[], bool]],
        get_status_callback: Optional[Callable[[], dict]],
        allow_lan: bool = False,
    ):
        self.api_token = api_token or ""
        self.sync_callback = sync_callback
        self.get_log_callback = get_log_callback
        self.pipeline_busy_callback = pipeline_busy_callback
        self.get_status_callback = get_status_callback
        self.allow_lan = allow_lan
        super().__init__(server_address, DashboardHandler)

    @property
    def ctx(self) -> "_DashboardHTTPServer":
        return self


class DashboardHandler(BaseHTTPRequestHandler):
    @property
    def _ctx(self) -> _DashboardHTTPServer:
        return self.server  # type: ignore[return-value]

    def log_message(self, format, *args):
        pass

    def _get_cookie(self, name: str) -> str | None:
        raw = self.headers.get("Cookie", "")
        if not raw:
            return None
        jar = http.cookies.SimpleCookie()
        jar.load(raw)
        if name in jar:
            return jar[name].value
        return None

    def _is_authenticated(self) -> bool:
        token = self._ctx.api_token
        if not token:
            return False
        auth = self.headers.get("Authorization", "")
        if auth == f"Bearer {token}":
            return True
        session = self._get_cookie(_session_cookie_name)
        return session == _session_value(token)

    def _require_auth(self) -> bool:
        if self._is_authenticated():
            return True
        self.send_error(401, "Unauthorized")
        return False

    def _send_json(self, code: int, payload: dict):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_html(self, html: str):
        body = html.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/login"):
            self._send_html(_login_html())
        elif self.path in ("/dashboard",):
            if not self._require_auth():
                return
            self._send_html(_dashboard_html())
        elif self.path == "/api/log":
            if not self._require_auth():
                return
            log_text = ""
            if self._ctx.get_log_callback:
                log_text = self._ctx.get_log_callback() or ""
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
            self._send_json(200, {"log": log_text})
        elif self.path == "/api/status":
            if not self._require_auth():
                return
            status = {"running": False, "last_result": {}}
            if self._ctx.pipeline_busy_callback:
                status["running"] = self._ctx.pipeline_busy_callback()
            if self._ctx.get_status_callback:
                status["last_result"] = self._ctx.get_status_callback()
            self._send_json(200, status)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == "/api/login":
            token = self._ctx.api_token
            if not token:
                self._send_json(503, {"error": "API 토큰이 설정되지 않았습니다."})
                return
            auth = self.headers.get("Authorization", "")
            token_ok = auth == f"Bearer {token}"
            if not token_ok:
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8") if length else "{}"
                    data = json.loads(body or "{}")
                    token_ok = data.get("token") == token
                except Exception:
                    token_ok = False
            if not token_ok:
                self._send_json(401, {"error": "잘못된 API 토큰입니다."})
                return
            session_val = _session_value(token)
            cookie_flags = "Path=/; HttpOnly; SameSite=Strict"
            if self._ctx.allow_lan:
                cookie_flags += "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Set-Cookie",
                f"{_session_cookie_name}={session_val}; {cookie_flags}",
            )
            self.send_header("Content-Length", "18")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        elif self.path == "/api/sync":
            if not self._require_auth():
                return
            busy_cb = self._ctx.pipeline_busy_callback
            if busy_cb and busy_cb():
                self._send_json(200, {"message": "⚠️ 동기화가 이미 실행 중입니다."})
                return
            msg = "동기화가 백그라운드에서 시작됩니다."
            sync_cb = self._ctx.sync_callback
            if sync_cb:
                threading.Thread(target=sync_cb, daemon=True).start()
            self._send_json(200, {"message": f"✅ {msg}"})
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
        get_status_callback: Optional[Callable[[], dict]] = None,
        allow_lan: bool = False,
    ):
        self.port = port
        self.bind_host = bind_host
        self.api_token = api_token or ""
        self.sync_callback = sync_callback
        self.get_log_callback = get_log_callback
        self.pipeline_busy_callback = pipeline_busy_callback
        self.get_status_callback = get_status_callback
        self.allow_lan = allow_lan
        self._server: Optional[_DashboardHTTPServer] = None
        self._running = False

    def start(self) -> bool:
        if self._running:
            return True
        if not self.api_token:
            print("❌ 웹 대시보드: API 토큰이 없습니다. config.json을 확인하세요.")
            return False
        try:
            self._server = _DashboardHTTPServer(
                (self.bind_host, self.port),
                self.api_token,
                self.sync_callback,
                self.get_log_callback,
                self.pipeline_busy_callback,
                self.get_status_callback,
                self.allow_lan,
            )
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