"""웹 대시보드 HTTP 요청 핸들러."""
from __future__ import annotations

import json
import os
import threading
import http.cookies
from http.server import BaseHTTPRequestHandler
from typing import TYPE_CHECKING

from websync.servers.dashboard.session import (
    SESSION_COOKIE_NAME,
    SESSION_MAX_AGE_SEC,
    session_value,
    session_valid,
    token_matches,
)
from websync.servers.dashboard.templates_loader import login_html, dashboard_html

if TYPE_CHECKING:
    from websync.servers.dashboard.http_server import DashboardHTTPServer


class DashboardHandler(BaseHTTPRequestHandler):
    @property
    def _ctx(self) -> "DashboardHTTPServer":
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
        if auth.startswith("Bearer ") and token_matches(auth[7:].strip(), token):
            return True
        session = self._get_cookie(SESSION_COOKIE_NAME)
        return session_valid(token, session)

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
            self._send_html(login_html())
        elif self.path in ("/dashboard",):
            if not self._require_auth():
                return
            self._send_html(dashboard_html())
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
            token_ok = auth.startswith("Bearer ") and token_matches(auth[7:].strip(), token)
            if not token_ok:
                try:
                    length = int(self.headers.get("Content-Length", 0))
                    body = self.rfile.read(length).decode("utf-8") if length else "{}"
                    data = json.loads(body or "{}")
                    token_ok = token_matches(str(data.get("token") or ""), token)
                except Exception:
                    token_ok = False
            if not token_ok:
                self._send_json(401, {"error": "잘못된 API 토큰입니다."})
                return
            session_val = session_value(token)
            cookie_flags = (
                f"Path=/; HttpOnly; SameSite=Strict; Max-Age={SESSION_MAX_AGE_SEC}"
            )
            if self._ctx.allow_lan:
                cookie_flags += "; Secure" if self.headers.get("X-Forwarded-Proto") == "https" else ""
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header(
                "Set-Cookie",
                f"{SESSION_COOKIE_NAME}={session_val}; {cookie_flags}",
            )
            self.send_header("Content-Length", "18")
            self.end_headers()
            self.wfile.write(b'{"ok": true}')
        elif self.path == "/api/sync":
            if not self._require_auth():
                return
            busy_cb = self._ctx.pipeline_busy_callback
            if busy_cb and busy_cb():
                self._send_json(409, {"ok": False, "message": "⚠️ 동기화가 이미 실행 중입니다."})
                return
            sync_cb = self._ctx.sync_callback
            if not sync_cb:
                self._send_json(503, {"ok": False, "message": "동기화 콜백이 설정되지 않았습니다."})
                return

            # 기동 직전 재확인 (TOCTOU 완화) — 실제 락은 run_sync_pipeline 내부
            if busy_cb and busy_cb():
                self._send_json(409, {"ok": False, "message": "⚠️ 동기화가 이미 실행 중입니다."})
                return

            started = {"ok": False}

            def _run():
                try:
                    # sync_cb 가 False 를 반환하면 락 실패/이미 실행 중
                    result = sync_cb()
                    started["ok"] = bool(result) if result is not None else True
                except Exception:
                    started["ok"] = False

            threading.Thread(target=_run, daemon=True).start()
            self._send_json(
                202,
                {
                    "ok": True,
                    "message": "✅ 동기화가 백그라운드에서 시작됩니다.",
                },
            )
        else:
            self.send_error(404)
