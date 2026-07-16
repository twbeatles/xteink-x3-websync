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


class AppSyncControlMixin:
    def _run_immediate_sync(self):
        self._save_ui_settings()
        self._set_sync_ui_busy(True)
        self.bottom_bar.progress_bar["value"] = 0
        self._log_message("\n=== 동기화 실행 요청 받음 ===")

        def run():
            self.service.run_sync_pipeline(
                log_callback=self._make_log_callback(),
                progress_callback=self._make_progress_callback(),
            )
            self.root.after(0, self._sync_finished_ui)

        threading.Thread(target=run, daemon=True).start()

    def _sync_finished_ui(self):
        maximum = float(self.bottom_bar.progress_bar["maximum"] or 0)
        if maximum > 0:
            self.bottom_bar.progress_bar["value"] = maximum
            self.root.after(1500, lambda: self.bottom_bar.progress_bar.configure(value=0))
        else:
            self.bottom_bar.progress_bar["value"] = 0
        self._set_sync_ui_busy(False)
        self._log_message("=== 동기화 프로세스 종료 ===\n")
        self.tab_history._refresh_history()

    # ------------------------------------------------------------------
    # 종료 처리
    # ------------------------------------------------------------------

    def _on_close(self):
        if self._opds_server:
            self._opds_server.stop()
        if self._web_dashboard:
            self._web_dashboard.stop()
        if self._calibre_watcher:
            self._calibre_watcher.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()

