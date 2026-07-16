"""웹 대시보드 HTTPServer 래퍼."""
from __future__ import annotations

from http.server import HTTPServer
from typing import Callable, Optional

from websync.servers.dashboard.handler import DashboardHandler


class DashboardHTTPServer(HTTPServer):
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
    def ctx(self) -> "DashboardHTTPServer":
        return self
