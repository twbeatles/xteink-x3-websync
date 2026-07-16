"""메인 GUI 컨트롤러 (조립)."""
from __future__ import annotations

import os
import hashlib
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from websync.integrations.calibre import CalibreManager
from websync.core.paths import resolve_path
from websync.upload.uploader import X3Uploader, normalize_device_host
from websync.scheduler.manager import SchedulerManager
from websync.integrations.notifier import ToastNotifier
from websync.pipeline.service import SyncService
from websync.core.logger import get_log_dir
from websync.config.exceptions import ConfigSaveError
from websync.gui.widgets import (
    BG_COLOR, FG_COLOR, ACCENT_COLOR, SECONDARY_BG, TEXT_BG, GREEN_COLOR, RED_COLOR, YELLOW_COLOR, HINT_COLOR,
    center_window, setup_dialog
)
from websync.gui.tab_sync import SyncTab
from websync.gui.tab_calibre import CalibreTab
from websync.gui.tab_history import HistoryTab
from websync.gui.tab_device_files import DeviceFilesTab
from websync.gui.tab_settings import SettingsTab
from websync.gui.bottom_bar import BottomBar

from websync.gui.app_core.layout import AppLayoutMixin
from websync.gui.app_core.helpers import AppHelpersMixin
from websync.gui.app_core.config_sync import AppConfigSyncMixin
from websync.gui.app_core.sync_control import AppSyncControlMixin


class SyncAppGui(
    AppLayoutMixin,
    AppHelpersMixin,
    AppConfigSyncMixin,
    AppSyncControlMixin,
):
    """Tkinter 탭형 인터페이스 및 동기화 비즈니스 중개 GUI 컨트롤러"""
    def __init__(self, service: SyncService):
        self.service = service
        self.scheduler = SchedulerManager()
        self.calibre = CalibreManager(
            self.service.config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"),
            self.service.config.get("calibre_library_path", ""),
        )

        # 서버 인스턴스
        self._opds_server = None
        self._web_dashboard = None
        self._calibre_watcher = None

        self.root = tk.Tk()
        self.root.title("Xteink X3 WebSync Manager")
        # 고 DPI(125%/150%/200%)에서도 하단 동기화 바가 잘리지 않도록
        # 화면 비율 기반으로 초기 크기를 잡고, 최소 높이를 충분히 확보한다.
        init_w, init_h = self._preferred_window_size()
        self.root.geometry(f"{init_w}x{init_h}")
        self.root.minsize(720, 620)
        self.root.resizable(True, True)

        self._sync_busy = False
        self._bottom_pane_adjusted = False

        self._setup_styles()
        self._build_ui()
        self._load_config_to_ui()

        self.root.after(0, lambda w=init_w, h=init_h: self._finalize_layout(w, h))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

