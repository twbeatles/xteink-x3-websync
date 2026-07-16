"""X3 WebSync 경량 웹 대시보드 서버 (하위 호환 진입점)."""
from websync.servers.dashboard import WebDashboard, DashboardHandler, DashboardHTTPServer
from websync.servers.dashboard.session import (
    SESSION_COOKIE_NAME as _session_cookie_name,
    SESSION_MAX_AGE_SEC as _SESSION_MAX_AGE_SEC,
    session_value as _session_value,
    session_valid as _session_valid,
    token_matches as _token_matches,
)
from websync.servers.dashboard.templates_loader import (
    load_template as _load_template,
    login_html as _login_html,
    dashboard_html as _dashboard_html,
)
from websync.servers.dashboard.http_server import DashboardHTTPServer as _DashboardHTTPServer

__all__ = [
    "WebDashboard",
    "DashboardHandler",
    "DashboardHTTPServer",
    "_DashboardHTTPServer",
    "_load_template",
    "_session_value",
    "_session_valid",
    "_token_matches",
    "_login_html",
    "_dashboard_html",
    "_session_cookie_name",
    "_SESSION_MAX_AGE_SEC",
]
