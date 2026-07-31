"""공유 데이터 폴더 (OneDrive 등) 설정 UI (CustomTkinter 카드 기반)."""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

from websync.backup.portable_cfg import (
    HISTORY_MODE_GLOBAL_URL,
    HISTORY_MODE_PER_DEVICE,
    apply_portable_cfg,
    get_portable_cfg,
    normalize_history_mode,
)
from websync.gui.widgets import (
    CardFrame, COLOR_CARD_BG, COLOR_FG, COLOR_SECONDARY_FG, COLOR_ACCENT,
    COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING, get_font
)


_HISTORY_MODE_LABELS = {
    HISTORY_MODE_PER_DEVICE: "기기별 이력 (같은 리더기만 스킵)",
    HISTORY_MODE_GLOBAL_URL: "URL 전역 이력 (한 번 보낸 글은 모두 스킵)",
}
_LABEL_TO_MODE = {v: k for k, v in _HISTORY_MODE_LABELS.items()}


class SettingsBackupSyncMixin:
    def _build_backup_sync_section(self, body) -> None:
        card = CardFrame(body, title="☁ 공유 데이터 폴더 (OneDrive / Google Drive 등)", subtitle="구독 목록 및 이력 멀티 PC 공유")
        card.pack(fill="x", padx=8, pady=6)

        inner = ctk.CTkFrame(card, fg_color="transparent")
        inner.pack(fill="x", padx=12, pady=10)
        inner.columnconfigure(1, weight=1)

        ctk.CTkLabel(
            inner,
            text="사이트 구독 목록과 전송 이력의 공식 저장소입니다. "
                 "PC를 바꿔도 이 폴더만 연결하면 새 글만 동기화됩니다.",
            font=get_font(12),
            text_color=COLOR_SECONDARY_FG,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, padx=4, pady=(0, 6), sticky="w")

        self.backup_enabled_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(
            inner,
            text="공유 데이터 폴더 사용",
            font=get_font(12),
            variable=self.backup_enabled_var,
            command=self._save_backup_sync_settings,
        ).grid(row=1, column=0, columnspan=2, padx=4, pady=4, sticky="w")

        ctk.CTkLabel(inner, text="데이터 폴더:", font=get_font(13)).grid(row=2, column=0, padx=(0, 6), pady=6, sticky="w")
        self.backup_folder_entry = ctk.CTkEntry(inner, font=get_font(12), height=34)
        self.backup_folder_entry.grid(row=2, column=1, padx=4, pady=6, sticky="we")
        ctk.CTkButton(inner, text="폴더 선택", font=get_font(12), width=90, height=34, command=self._browse_backup_folder).grid(
            row=2, column=2, padx=4, pady=6
        )
        ctk.CTkButton(inner, text="폴더 열기", font=get_font(12), width=90, height=34, fg_color=("#e9ecef", "#343a40"), text_color=COLOR_FG, command=self._open_backup_folder).grid(
            row=2, column=3, padx=4, pady=6
        )
        self.app._bind_autosave(self.backup_folder_entry)

        self.backup_include_history_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            inner,
            text="전송 이력(synced_posts.json) 포함",
            font=get_font(12),
            variable=self.backup_include_history_var,
            command=self._save_backup_sync_settings,
        ).grid(row=3, column=0, columnspan=2, padx=4, pady=2, sticky="w")

        self.backup_auto_import_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            inner,
            text="시작 시 / 동기화 전 가져오기",
            font=get_font(12),
            variable=self.backup_auto_import_var,
            command=self._save_backup_sync_settings,
        ).grid(row=4, column=0, columnspan=2, padx=4, pady=2, sticky="w")

        self.backup_auto_export_var = tk.BooleanVar(value=True)
        ctk.CTkCheckBox(
            inner,
            text="변경·동기화 후 자동 내보내기",
            font=get_font(12),
            variable=self.backup_auto_export_var,
            command=self._save_backup_sync_settings,
        ).grid(row=5, column=0, columnspan=2, padx=4, pady=2, sticky="w")

        ctk.CTkLabel(inner, text="이력 판정 모드:", font=get_font(13)).grid(row=6, column=0, padx=(0, 6), pady=6, sticky="w")
        self.backup_history_mode_cb = ctk.CTkOptionMenu(
            inner,
            values=list(_HISTORY_MODE_LABELS.values()),
            font=get_font(12),
            width=340,
            command=lambda _v: self._save_backup_sync_settings()
        )
        self.backup_history_mode_cb.set(_HISTORY_MODE_LABELS[HISTORY_MODE_PER_DEVICE])
        self.backup_history_mode_cb.grid(row=6, column=1, columnspan=2, padx=4, pady=6, sticky="w")

        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.pack(fill="x", padx=12, pady=(0, 8))

        ctk.CTkButton(
            btn_row,
            text="☁ 지금 공유 폴더와 동기화 (Pull & Push)",
            font=get_font(13, "bold"),
            fg_color=COLOR_ACCENT[0],
            hover_color=COLOR_ACCENT[1],
            height=38,
            command=self._run_backup_sync_now,
        ).pack(side="left", padx=4)

        self.backup_status_label = ctk.CTkLabel(
            btn_row,
            text="",
            font=get_font(12),
            text_color=COLOR_SECONDARY_FG,
        )
        self.backup_status_label.pack(side="left", padx=10)

    def _browse_backup_folder(self):
        d = filedialog.askdirectory(title="공유 데이터 폴더 선택 (OneDrive 등)")
        if d:
            self.backup_folder_entry.delete(0, tk.END)
            self.backup_folder_entry.insert(0, d)
            self._save_backup_sync_settings()

    def _open_backup_folder(self):
        folder = self.backup_folder_entry.get().strip()
        if not folder or not os.path.isdir(folder):
            messagebox.showwarning("경고", "올바른 공유 폴더가 설정되지 않았습니다.")
            return
        try:
            if os.name == "nt":
                os.startfile(folder)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("오류", f"폴더 열기 실패: {e}")

    def _collect_backup_sync_into_config(self, config: dict) -> None:
        mode_label = ""
        if hasattr(self, "backup_history_mode_cb"):
            mode_label = self.backup_history_mode_cb.get()
        mode = _LABEL_TO_MODE.get(mode_label, HISTORY_MODE_PER_DEVICE)
        apply_portable_cfg(
            config,
            {
                "enabled": bool(self.backup_enabled_var.get()),
                "folder": self.backup_folder_entry.get().strip(),
                "include_history": bool(self.backup_include_history_var.get()),
                "auto_import_on_start": bool(self.backup_auto_import_var.get()),
                "auto_export": bool(self.backup_auto_export_var.get()),
                "history_mode": normalize_history_mode(mode),
            },
        )

    def _save_backup_sync_settings(self):
        config = self.service.config
        self._collect_backup_sync_into_config(config)
        if not self.app._safe_save_config(config, reload=True):
            return
        self._refresh_backup_status_label()
        self.app._log_message("☁ 공유 데이터 폴더 설정을 저장했습니다.")

    def _load_backup_sync_from_config(self, config: dict) -> None:
        bs = get_portable_cfg(config)
        self.backup_enabled_var.set(bool(bs.get("enabled", False)))
        self.backup_folder_entry.delete(0, tk.END)
        self.backup_folder_entry.insert(0, bs.get("folder", "") or "")
        self.backup_include_history_var.set(bool(bs.get("include_history", True)))
        self.backup_auto_import_var.set(bool(bs.get("auto_import_on_start", True)))
        self.backup_auto_export_var.set(bool(bs.get("auto_export", True)))
        m = normalize_history_mode(bs.get("history_mode"))
        label = _HISTORY_MODE_LABELS.get(m, _HISTORY_MODE_LABELS[HISTORY_MODE_PER_DEVICE])
        if hasattr(self, "backup_history_mode_cb"):
            self.backup_history_mode_cb.set(label)
        self._refresh_backup_status_label(config)

    def _refresh_backup_status_label(self, config: dict | None = None) -> None:
        cfg = config or self.service.config
        bs = get_portable_cfg(cfg)
        hm = normalize_history_mode(bs.get("history_mode"))
        mode_label = "기기별" if hm == HISTORY_MODE_PER_DEVICE else "전역URL"
        last = bs.get("last_sync_at") or ""

        if bs.get("enabled") and last:
            text = f"상태: 마지막 동기화 {last}  |  모드: {mode_label}"
            color = COLOR_SUCCESS[0]
        elif bs.get("enabled") and bs.get("folder"):
            text = f"활성화됨 — 아직 동기화 기록이 없습니다.  |  모드: {mode_label}"
            color = COLOR_ACCENT[0]
        else:
            text = "비활성 — 공유 데이터 폴더를 지정하고 사용을 켜 주세요."
            color = COLOR_SECONDARY_FG
        self.backup_status_label.configure(text=text, text_color=color)

    def _run_backup_sync_now(self):
        self._save_backup_sync_settings()
        config = self.service.config
        bs = get_portable_cfg(config)
        if not (bs.get("folder") or "").strip():
            messagebox.showwarning("폴더 필요", "데이터 폴더를 먼저 선택해 주세요.")
            return

        self.backup_status_label.configure(text="동기화 중…", text_color=COLOR_ACCENT[0])
        self.app._log_message("☁ 공유 데이터 폴더 동기화를 실행합니다...")

        def task():
            try:
                result = self.service.run_backup_sync_now(
                    log_callback=self.app._make_log_callback()
                )
                ok = bool(result.get("ok"))
                pull = result.get("pull") or {}
                push = result.get("push") or {}
                msg = f"{pull.get('message', '')} / {push.get('message', '')}".strip(" /")

                def done():
                    self.service._reload_config()
                    self._refresh_backup_status_label()
                    try:
                        self.app.tab_sync._refresh_site_tree()
                        self.app.tab_history._refresh_history()
                    except Exception:
                        pass
                    if ok:
                        messagebox.showinfo("공유 데이터 동기화 완료", msg or "동기화가 완료되었습니다.")
                    else:
                        messagebox.showerror(
                            "공유 데이터 동기화 실패",
                            msg or "동기화에 실패했습니다. 로그를 확인하세요.",
                        )
                        self.backup_status_label.configure(
                            text=msg or "동기화 실패", text_color=COLOR_DANGER[0]
                        )

                self.app.root.after(0, done)
            except Exception as e:
                def err():
                    messagebox.showerror("공유 데이터 동기화 오류", str(e))
                    self.backup_status_label.configure(text=str(e), text_color=COLOR_DANGER[0])

                self.app.root.after(0, err)

        threading.Thread(target=task, daemon=True).start()
