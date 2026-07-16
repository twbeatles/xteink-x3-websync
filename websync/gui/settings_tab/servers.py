from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.gui.widgets import (
    RED_COLOR, GREEN_COLOR, ACCENT_COLOR, HINT_COLOR, BG_COLOR,
    create_scrollable_frame, setup_dialog
)
from websync.core.paths import resolve_path
from websync.core.logger import get_log_dir
from websync.servers.opds import OPDSServer
from websync.servers.web_dashboard import WebDashboard
from websync.watch.calibre import CalibreWatcher


class SettingsServersMixin:
    def _toggle_opds(self):
        if self.app._opds_server and self.app._opds_server.is_running:
            self.app._opds_server.stop()
            self.app._opds_server = None
            self.opds_start_btn.config(text="▶ 서버 시작")
            self.opds_status_label.config(text="중지됨", foreground=RED_COLOR)
            self.opds_url_label.config(text="")
        else:
            try:
                port = int(self.opds_port_sp.get())
            except ValueError:
                port = 8765
            output_dir = resolve_path(self.app.tab_sync.dir_entry.get().strip() or "./output")
            allow_lan = self.opds_allow_lan_var.get()
            bind_host = "0.0.0.0" if allow_lan else "127.0.0.1"
            config = self.config_manager.load_config()
            opds_conf = config.get("opds_server", {})
            api_key = opds_conf.get("api_key", "")
            self.app._opds_server = OPDSServer(
                output_dir=output_dir,
                port=port,
                bind_host=bind_host,
                api_key=api_key,
                require_auth=allow_lan,
            )
            if self.app._opds_server.start():
                self.opds_start_btn.config(text="■ 서버 중지")
                self.opds_status_label.config(text="실행 중 ✅", foreground=GREEN_COLOR)
                url = self.app._opds_server.get_url()
                self.opds_url_label.config(text=url)
                self.app._log_message(f"📡 OPDS 서버 시작: {url}")
            else:
                messagebox.showerror("오류", f"OPDS 서버 시작 실패. 포트 {port}이 이미 사용 중일 수 있습니다.")

    def _toggle_web(self):
        if self.app._web_dashboard and self.app._web_dashboard.is_running:
            self.app._web_dashboard.stop()
            self.app._web_dashboard = None
            self.web_start_btn.config(text="▶ 서버 시작")
            self.web_status_label.config(text="중지됨", foreground=RED_COLOR)
            self.web_url_label.config(text="")
        else:
            try:
                port = int(self.web_port_sp.get())
            except ValueError:
                port = 8766

            config = self.config_manager.load_config()
            web_conf = config.get("web_dashboard", {})
            api_token = web_conf.get("api_token", "")
            bind_host = "0.0.0.0" if self.web_allow_lan_var.get() else "127.0.0.1"

            def sync_cb():
                self.service.run_sync_pipeline(log_callback=self.app._make_log_callback())

            self.app._web_dashboard = WebDashboard(
                port=port,
                bind_host=bind_host,
                api_token=api_token,
                sync_callback=sync_cb,
                get_log_callback=self.app._get_log_for_web,
                pipeline_busy_callback=self.service.is_pipeline_running,
                get_status_callback=self.service.get_last_pipeline_result,
                allow_lan=self.web_allow_lan_var.get(),
            )
            if self.web_allow_lan_var.get():
                if not messagebox.askyesno(
                    "LAN 공개 경고",
                    "LAN 공개 모드는 HTTP 평문으로 API 토큰이 전송됩니다.\n"
                    "신뢰할 수 있는 네트워크에서만 계속하시겠습니까?",
                    icon="warning",
                ):
                    return
            if self.app._web_dashboard.start():
                self.web_start_btn.config(text="■ 서버 중지")
                self.web_status_label.config(text="실행 중 ✅", foreground=GREEN_COLOR)
                url = self.app._web_dashboard.get_url()
                self.web_url_label.config(text=url)
                self.app._log_message(f"🌐 웹 대시보드 시작: {url}")
            else:
                messagebox.showerror("오류", f"웹 대시보드 시작 실패. 포트 {port}이 이미 사용 중일 수 있습니다.")

