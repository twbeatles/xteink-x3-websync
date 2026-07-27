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
from websync.config.secrets import mask_secret


class SettingsAiTranslationMixin:
    def _save_ai_settings(self):
        config = self.service.config
        config["ai_summary"] = {
            "enabled": self.ai_enabled_var.get(),
            "provider": self.ai_provider_cb.get(),
            "api_key": self.ai_key_entry.get().strip(),
            "model": config.get("ai_summary", {}).get("model", "gpt-4o-mini"),
            "ollama_host": config.get("ai_summary", {}).get("ollama_host", "http://localhost:11434"),
        }
        if not self.app._safe_save_config(config):
            return
        messagebox.showinfo("저장 완료", "AI 요약 설정이 저장되었습니다.")

    def _save_trans_settings(self):
        config = self.service.config
        # provider=libretranslate 일 때만 입력값 사용, 아니면 기존값 유지
        if self.trans_provider_cb.get() == "libretranslate":
            api_key = self.trans_key_entry.get().strip()
        else:
            api_key = config.get("translation", {}).get("libretranslate_api_key", "")
        config["translation"] = {
            "enabled": self.trans_enabled_var.get(),
            "provider": self.trans_provider_cb.get(),
            "libretranslate_host": config.get("translation", {}).get("libretranslate_host", "http://localhost:5000"),
            "libretranslate_api_key": api_key,
        }
        if not self.app._safe_save_config(config):
            return
        messagebox.showinfo("저장 완료", "번역 설정이 저장되었습니다.")

    # ------------------------------------------------------------------
    # N5: 시크릿 입력 보기/숨기기 토글
    # ------------------------------------------------------------------
    def _toggle_ai_key_visibility(self) -> None:
        self.ai_key_entry.config(show="" if self.ai_key_show_var.get() else "*")

    def _toggle_trans_key_visibility(self) -> None:
        self.trans_key_entry.config(show="" if self.trans_key_show_var.get() else "*")

    def _update_trans_key_state(self) -> None:
        """provider=libretranslate 일 때만 API Key Entry 활성."""
        is_libre = self.trans_provider_cb.get() == "libretranslate"
        state = "normal" if is_libre else "disabled"
        self.trans_key_entry.config(state=state)

    def _refresh_opds_key_display(self) -> None:
        """OPDS API 키를 마스킹(기본) 또는 평문(표시 토글)으로 갱신."""
        config = self.service.config_manager.load_config()
        key = (config.get("opds_server") or {}).get("api_key", "")
        if not key:
            self.opds_api_key_label.config(text="(자동 생성됨)")
            return
        shown = key if self.opds_key_show_var.get() else mask_secret(key)
        label = f"API 키: {shown}" if self.opds_key_show_var.get() else f"API 키: {shown} (표시 체크로 전체 확인)"
        self.opds_api_key_label.config(text=label)

    def _refresh_web_token_display(self) -> None:
        """웹 대시보드 토큰을 마스킹(기본) 또는 평문(표시 토글)으로 갱신."""
        config = self.service.config_manager.load_config()
        token = (config.get("web_dashboard") or {}).get("api_token", "")
        if not token:
            self.web_token_label.config(text="(자동 생성됨)")
            return
        shown = token if self.web_token_show_var.get() else mask_secret(token)
        label = f"토큰: {shown}" if self.web_token_show_var.get() else f"토큰: {shown} (표시 체크로 전체 확인)"
        self.web_token_label.config(text=label)

    def _open_log_folder(self):
        folder = get_log_dir()
        os.makedirs(folder, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif os.sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("오류", f"로그 폴더를 열 수 없습니다: {e}")

