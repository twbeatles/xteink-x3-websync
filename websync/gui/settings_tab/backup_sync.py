"""클라우드 백업 동기화 (OneDrive 등) 설정 UI."""
from __future__ import annotations

import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.gui.widgets import HINT_COLOR, GREEN_COLOR, RED_COLOR, ACCENT_COLOR


class SettingsBackupSyncMixin:
    def _build_backup_sync_section(self, body: ttk.Frame) -> None:
        frame = ttk.LabelFrame(body, text=" ☁ 클라우드 백업 동기화 (OneDrive 등) ")
        frame.pack(fill="x", padx=15, pady=10)
        frame.columnconfigure(1, weight=1)

        ttk.Label(
            frame,
            text="사이트 구독 목록과 전송 이력(JSON)을 지정 폴더에 미러합니다. "
                 "기기 IP·Calibre 경로·API 키는 포함하지 않습니다.",
            font=("Malgun Gothic", 8),
            foreground=HINT_COLOR,
            wraplength=640,
            justify="left",
        ).grid(row=0, column=0, columnspan=4, padx=10, pady=(8, 4), sticky="w")

        self.backup_enabled_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            frame,
            text="백업 동기화 사용",
            variable=self.backup_enabled_var,
            command=self._save_backup_sync_settings,
        ).grid(row=1, column=0, columnspan=2, padx=10, pady=4, sticky="w")

        ttk.Label(frame, text="동기화 폴더:").grid(row=2, column=0, padx=10, pady=6, sticky="w")
        self.backup_folder_entry = ttk.Entry(frame)
        self.backup_folder_entry.grid(row=2, column=1, padx=5, pady=6, sticky="we")
        ttk.Button(frame, text="폴더 선택", command=self._browse_backup_folder).grid(
            row=2, column=2, padx=5, pady=6
        )
        ttk.Button(frame, text="폴더 열기", command=self._open_backup_folder).grid(
            row=2, column=3, padx=5, pady=6
        )
        self.app._bind_autosave(self.backup_folder_entry)

        self.backup_include_history_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="전송 이력(synced_posts.json) 포함",
            variable=self.backup_include_history_var,
            command=self._save_backup_sync_settings,
        ).grid(row=3, column=0, columnspan=2, padx=10, pady=2, sticky="w")

        self.backup_auto_import_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="시작 시 / 동기화 전 가져오기",
            variable=self.backup_auto_import_var,
            command=self._save_backup_sync_settings,
        ).grid(row=4, column=0, columnspan=2, padx=10, pady=2, sticky="w")

        self.backup_auto_export_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            frame,
            text="변경·동기화 후 자동 내보내기",
            variable=self.backup_auto_export_var,
            command=self._save_backup_sync_settings,
        ).grid(row=5, column=0, columnspan=2, padx=10, pady=2, sticky="w")

        btn_row = ttk.Frame(frame)
        btn_row.grid(row=6, column=0, columnspan=4, padx=10, pady=8, sticky="w")
        ttk.Button(btn_row, text="지금 동기화", command=self._run_backup_sync_now).pack(side="left", padx=3)
        ttk.Button(btn_row, text="설정 저장", command=self._save_backup_sync_settings).pack(side="left", padx=3)

        self.backup_status_label = ttk.Label(frame, text="", foreground=HINT_COLOR, wraplength=640)
        self.backup_status_label.grid(row=7, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="w")

    def _browse_backup_folder(self):
        path = filedialog.askdirectory(title="클라우드 백업 동기화 폴더 선택")
        if not path:
            return
        self.backup_folder_entry.delete(0, "end")
        self.backup_folder_entry.insert(0, path)
        self._save_backup_sync_settings()

    def _open_backup_folder(self):
        folder = self.backup_folder_entry.get().strip()
        if not folder:
            messagebox.showinfo("안내", "동기화 폴더를 먼저 지정해 주세요.")
            return
        if not os.path.isdir(folder):
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as e:
                messagebox.showerror("오류", f"폴더를 만들 수 없습니다:\n{e}")
                return
        try:
            if sys.platform == "win32":
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
        bs = config.setdefault("backup_sync", {})
        if not isinstance(bs, dict):
            bs = {}
            config["backup_sync"] = bs
        bs["enabled"] = bool(self.backup_enabled_var.get())
        bs["folder"] = self.backup_folder_entry.get().strip()
        bs["include_history"] = bool(self.backup_include_history_var.get())
        bs["auto_import_on_start"] = bool(self.backup_auto_import_var.get())
        bs["auto_export"] = bool(self.backup_auto_export_var.get())

    def _save_backup_sync_settings(self):
        config = self.service.config
        self._collect_backup_sync_into_config(config)
        if not self.app._safe_save_config(config, reload=True):
            return
        self._refresh_backup_status_label()
        self.app._log_message("☁ 클라우드 백업 동기화 설정을 저장했습니다.")

    def _load_backup_sync_from_config(self, config: dict) -> None:
        bs = config.get("backup_sync") if isinstance(config.get("backup_sync"), dict) else {}
        self.backup_enabled_var.set(bool(bs.get("enabled", False)))
        self.backup_folder_entry.delete(0, "end")
        self.backup_folder_entry.insert(0, bs.get("folder", "") or "")
        self.backup_include_history_var.set(bool(bs.get("include_history", True)))
        self.backup_auto_import_var.set(bool(bs.get("auto_import_on_start", True)))
        self.backup_auto_export_var.set(bool(bs.get("auto_export", True)))
        self._refresh_backup_status_label(config)

    def _refresh_backup_status_label(self, config: dict | None = None) -> None:
        cfg = config if config is not None else self.service.config
        bs = cfg.get("backup_sync") if isinstance(cfg.get("backup_sync"), dict) else {}
        last_at = bs.get("last_sync_at") or ""
        last_msg = bs.get("last_sync_message") or ""
        if last_at or last_msg:
            text = f"최근 동기화: {last_at}  {last_msg}".strip()
            color = GREEN_COLOR
        elif bs.get("enabled") and bs.get("folder"):
            text = "활성화됨 — 아직 동기화 기록이 없습니다. 「지금 동기화」를 눌러 주세요."
            color = ACCENT_COLOR
        else:
            text = "비활성 — OneDrive 등 폴더를 지정하고 사용을 켜 주세요."
            color = HINT_COLOR
        self.backup_status_label.config(text=text, foreground=color)

    def _run_backup_sync_now(self):
        # 현재 UI 값을 먼저 저장
        self._save_backup_sync_settings()
        config = self.service.config
        bs = config.get("backup_sync") or {}
        if not (bs.get("folder") or "").strip():
            messagebox.showwarning("폴더 필요", "동기화 폴더를 먼저 선택해 주세요.")
            return

        self.backup_status_label.config(text="동기화 중…", foreground=ACCENT_COLOR)
        self.app._log_message("☁ 클라우드 백업 동기화를 실행합니다...")

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
                    # 사이트가 바뀌었을 수 있음
                    try:
                        self.app.tab_sync._refresh_site_tree()
                        self.app.tab_history._refresh_history()
                    except Exception:
                        pass
                    if ok:
                        messagebox.showinfo("백업 동기화 완료", msg or "동기화가 완료되었습니다.")
                    else:
                        messagebox.showerror(
                            "백업 동기화 실패",
                            msg or "동기화에 실패했습니다. 로그를 확인하세요.",
                        )
                        self.backup_status_label.config(
                            text=msg or "동기화 실패", foreground=RED_COLOR
                        )

                self.app.root.after(0, done)
            except Exception as e:
                def err():
                    messagebox.showerror("백업 동기화 오류", str(e))
                    self.backup_status_label.config(text=str(e), foreground=RED_COLOR)

                self.app.root.after(0, err)

        threading.Thread(target=task, daemon=True).start()
