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


class AppHelpersMixin:
    def _bind_autosave(self, widget: tk.Misc) -> None:
        widget.bind("<FocusOut>", lambda _e: self._save_ui_settings())

    def _set_sync_ui_busy(self, busy: bool) -> None:
        self._sync_busy = busy
        state = "disabled" if busy else "normal"
        
        # 각 탭의 활성 버튼 상태 제어
        self.bottom_bar.sync_now_btn.config(state=state)
        self.bottom_bar.preview_btn.config(state=state)
        self.tab_sync.direct_upload_btn.config(state=state)
        self.tab_sync.test_conn_btn.config(state=state)
        self.tab_calibre.calibre_send_btn.config(state=state)
        self.tab_calibre.calibre_conn_btn.config(state=state)

    def _log_message(self, message: str):
        self.bottom_bar.log_txt.config(state="normal")
        self.bottom_bar.log_txt.insert(tk.END, message + "\n")
        self.bottom_bar.log_txt.see(tk.END)
        self.bottom_bar.log_txt.config(state="disabled")

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.bottom_bar.progress_bar["maximum"] = total
            self.bottom_bar.progress_bar["value"] = current
        else:
            self.bottom_bar.progress_bar["value"] = 0

    def _open_url(self, url: str):
        if url:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass

    def _make_log_callback(self):
        return lambda msg: self.root.after(0, lambda m=msg: self._log_message(m))

    def _make_progress_callback(self):
        return lambda cur, tot: self.root.after(0, lambda c=cur, t=tot: self._update_progress(c, t))

    def _make_uploader(self) -> X3Uploader:
        config = self.service.config
        df = config.get("device_files") or {}
        return X3Uploader(
            config.get("x3_ip", "").strip() or self.tab_sync.ip_entry.get().strip(),
            config.get("x3_devices", []),
            remote_dir=df.get("default_upload_path", "/"),
        )

    def _ip_display_name(self, ip: str) -> str:
        for d in self._make_uploader()._build_target_list():
            if d["ip"] == ip:
                return d.get("name") or ip
        return ip

    def _summarize_upload_results(self, results: dict) -> tuple[bool, bool, str]:
        if not results:
            return False, False, "등록된 기기 없음"
        ok_labels = [f"{self._ip_display_name(ip)}({ip})" for ip, ok in results.items() if ok]
        fail_labels = [f"{self._ip_display_name(ip)}({ip})" for ip, ok in results.items() if not ok]
        parts = []
        if ok_labels:
            parts.append(f"성공: {', '.join(ok_labels)}")
        if fail_labels:
            parts.append(f"실패: {', '.join(fail_labels)}")
        return all(results.values()), bool(ok_labels), " | ".join(parts)

    def _safe_save_config(self, config: dict, *, parent=None, reload: bool = False) -> bool:
        try:
            self.service.config_manager.save_config(config)
            if reload:
                self.service._reload_config()
            return True
        except ConfigSaveError as e:
            messagebox.showerror("설정 저장 실패", str(e), parent=parent)
            self._log_message(f"❌ 설정 저장 실패: {e}")
            return False
        except Exception as e:
            messagebox.showerror("설정 저장 실패", str(e), parent=parent)
            self._log_message(f"❌ 설정 저장 실패: {e}")
            return False

    def _get_log_for_web(self) -> str:
        try:
            content = self.bottom_bar.log_txt.get("1.0", "end-1c")
            if content.strip():
                lines = content.splitlines()
                return "\n".join(lines[-100:])
        except Exception:
            pass
        log_dir = get_log_dir()
        if os.path.isdir(log_dir):
            files = sorted(os.listdir(log_dir), reverse=True)
            if files:
                try:
                    with open(os.path.join(log_dir, files[0]), "r", encoding="utf-8") as f:
                        return "".join(f.readlines()[-100:])
                except Exception:
                    pass
        return ""

    # ------------------------------------------------------------------
    # 설정 동기화 및 윈도우 컨트롤
    # ------------------------------------------------------------------

