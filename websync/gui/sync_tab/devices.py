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


class SyncDevicesMixin:
    def _refresh_devices_tree(self):
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)
        for idx, dev in enumerate(self.service.config.get("x3_devices", [])):
            self.devices_tree.insert("", "end", iid=str(idx), values=(
                dev.get("name", ""), dev.get("ip", "")
            ))

    def _add_device_popup(self):
        dialog = tk.Toplevel(self.app.root)
        dialog.title("X3 기기 추가")
        dialog.configure(bg=BG_COLOR)
        setup_dialog(dialog, self.app.root, 360, 180)
        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="기기 이름:").grid(row=0, column=0, sticky="w", pady=6)
        name_entry = ttk.Entry(frame, width=28)
        name_entry.grid(row=0, column=1, pady=6)
        ttk.Label(frame, text="IP/호스트:").grid(row=1, column=0, sticky="w", pady=6)
        ip_entry = ttk.Entry(frame, width=28)
        ip_entry.grid(row=1, column=1, pady=6)

        def save():
            from websync.upload.uploader import normalize_device_host

            name = name_entry.get().strip()
            ip = normalize_device_host(ip_entry.get())
            if not name or not ip:
                messagebox.showerror("오류", "이름과 IP를 모두 입력해 주세요.", parent=dialog)
                return
            config = self.service.config
            devices = config.setdefault("x3_devices", [])
            primary = normalize_device_host(config.get("x3_ip") or "")
            if ip == primary:
                messagebox.showwarning("중복", "기본 기기 IP와 동일합니다.", parent=dialog)
                return
            if any(normalize_device_host(d.get("ip")) == ip for d in devices):
                messagebox.showwarning("중복", "이미 등록된 IP입니다.", parent=dialog)
                return
            if name == "기본 기기" or any(d.get("name") == name for d in devices):
                messagebox.showwarning("중복", "이미 사용 중인 기기 이름입니다.", parent=dialog)
                return
            devices.append({"name": name, "ip": ip})
            if not self.app._safe_save_config(config, parent=dialog, reload=True):
                return
            self._refresh_devices_tree()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", pady=8)
        ttk.Button(btn_frame, text="저장", command=save).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="취소", command=dialog.destroy).pack(side="right")

    def _remove_device(self):
        selected = self.devices_tree.selection()
        if not selected:
            messagebox.showwarning("경고", "삭제할 기기를 선택해 주세요.")
            return
        config = self.service.config
        devices = config.get("x3_devices", [])
        indices = sorted([int(i) for i in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(devices):
                devices.pop(idx)
        config["x3_devices"] = devices
        if not self.app._safe_save_config(config, reload=True):
            return
        self._refresh_devices_tree()

    # ------------------------------------------------------------------
    # 사이트 관리
    # ------------------------------------------------------------------

