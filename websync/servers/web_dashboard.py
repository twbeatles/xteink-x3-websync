"""X3 WebSync 경량 웹 대시보드 서버"""
import os
import sys
import json
import hmac
import hashlib
import secrets
import threading
import time
import http.cookies
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional, Callable
from websync.core.logger import get_logger

logger = get_logger()
_session_cookie_name = "x3sync_session"
_SESSION_MAX_AGE_SEC = 7 * 24 * 3600  # 7일

def _load_template(name: str) -> str:
    """HTML 템플릿 파일을 읽어옵니다. sys.frozen 및 PyInstaller 대응."""
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            base_dir = os.path.join(sys._MEIPASS, "websync", "servers", "templates")
        else:
            base_dir = os.path.join(os.path.dirname(sys.executable), "servers", "templates")
    else:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "templates")
    
    path = os.path.join(base_dir, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"템플릿 로드 실패 ({name}): {e}")
        return f"Template {name} not found."



def _session_value(api_token: str, issued_at: int | None = None) -> str:
    """만료 가능한 세션 쿠키 값: {unix_ts}.{hmac}"""
    ts = int(issued_at if issued_at is not None else time.time())
    msg = f"x3websync-session-v2|{ts}".encode("utf-8")
    sig = hmac.new(api_token.encode("utf-8"), msg, hashlib.sha256).hexdigest()
    return f"{ts}.{sig}"


def _session_valid(api_token: str, cookie_val: str | None) -> bool:
    if not api_token or not cookie_val or "." not in cookie_val:
        return False
    try:
        ts_s, sig = cookie_val.split(".", 1)
        ts = int(ts_s)
        if time.time() - ts > _SESSION_MAX_AGE_SEC or ts > time.time() + 300:
            return False
        expected = _session_value(api_token, issued_at=ts)
        # compare full cookie to avoid partial leaks
        return secrets.compare_digest(cookie_val, expected)
    except (ValueError, TypeError):
        return False


def _token_matches(provided: str | None, expected: str) -> bool:
    if not provided or not expected:
        return False
    return secrets.compare_digest(provided, expected)


def _login_html() -> str:
    return _load_template("login.html")


def _dashboard_html() -> str:
    return _load_template("dashboard.html")



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
        if auth.startswith("Bearer ") and _token_matches(auth[7:].strip(), token):
            return True
        session = self._get_cookie(_session_cookie_name)
        return _session_valid(token, session)

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
            token_ok = auth.startswith("Bearer ") and _token_matches(auth[7:].strip(), token)
            if not token_ok:
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8") if length else "{}"
                    data = json.loads(body or "{}")
                    token_ok = _token_matches(str(data.get("token") or ""), token)
                except Exception:
                    token_ok = False
            if not token_ok:
                self._send_json(401, {"error": "잘못된 API 토큰입니다."})
                return
            session_val = _session_value(token)
            cookie_flags = (
                f"Path=/; HttpOnly; SameSite=Strict; Max-Age={_SESSION_MAX_AGE_SEC}"
            )
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
            logger.error("웹 대시보드: API 토큰이 없습니다. config.json을 확인하세요.")
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
            logger.error(f"웹 대시보드 서버 시작 실패: {e}")
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