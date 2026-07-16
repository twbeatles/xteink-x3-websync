from __future__ import annotations

import os
import sys
import hashlib
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.gui.widgets import (
    BG_COLOR, TEXT_BG, SECONDARY_BG, HINT_COLOR, YELLOW_COLOR, GREEN_COLOR, RED_COLOR,
    create_scrollable_frame, create_scrolled_tree, setup_dialog, bind_widget_mousewheel
)
from websync.upload.uploader import X3Uploader, normalize_device_host
from websync.config.exceptions import ConfigSaveError, ConfigLoadError


class SyncScheduleMixin:
    def _register_schedule(self):
        self.app._save_ui_settings()
        h, m = self.hour_cb.get(), self.min_cb.get()
        if self.scheduler.register_daily_task(h, m):
            messagebox.showinfo("스케줄러", f"매일 {h}:{m}에 백그라운드 동기화 스케줄이 등록되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = True
            self.app._safe_save_config(config)
        else:
            messagebox.showerror("스케줄러", "스케줄러 등록에 실패했습니다. 관리자 권한을 확인하세요.")
        self._refresh_schedule_status()

    def _unregister_schedule(self):
        if self.scheduler.unregister_task():
            messagebox.showinfo("스케줄러", "스케줄 작업이 해제되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = False
            self.app._safe_save_config(config)
        else:
            messagebox.showwarning("스케줄러", "스케줄 해제에 실패했거나 등록된 작업이 없습니다.")
        self._refresh_schedule_status()

    def _refresh_schedule_status(self):
        status = self.scheduler.get_task_status()
        self.sched_status_label.config(text=f"스케줄러 상태: {status}")

    # ------------------------------------------------------------------
    # 추가 기기 관리 팝업
    # ------------------------------------------------------------------

