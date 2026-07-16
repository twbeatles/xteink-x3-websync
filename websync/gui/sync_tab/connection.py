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


class SyncConnectionMixin:
    def _test_connection(self):
        self.conn_status_label.config(text="연결 중...", foreground=YELLOW_COLOR)
        self.test_conn_btn.config(state="disabled")

        def task():
            uploader = self.app._make_uploader()
            results = []
            for dev in uploader._build_target_list():
                ok = uploader.test_connection(dev["ip"])
                results.append((dev["name"], dev["ip"], ok))
            self.master.after(0, lambda: self._test_connection_finished(results))

        threading.Thread(target=task, daemon=True).start()

    def _test_connection_finished(self, results: list[tuple[str, str, bool]]):
        if not self.app._sync_busy:
            self.test_conn_btn.config(state="normal")
        if not results:
            self.conn_status_label.config(text="등록된 기기 없음", foreground=RED_COLOR)
            return
        ok_count = sum(1 for _, _, ok in results if ok)
        if ok_count == len(results):
            self.conn_status_label.config(text=f"전체 {len(results)}대 연결 성공 ✅", foreground=GREEN_COLOR)
        elif ok_count > 0:
            failed = [name for name, _, ok in results if not ok]
            self.conn_status_label.config(
                text=f"부분 성공 ({ok_count}/{len(results)}) — 실패: {', '.join(failed)}",
                foreground=YELLOW_COLOR,
            )
        else:
            self.conn_status_label.config(text="모든 기기 연결 실패 ❌", foreground=RED_COLOR)
        for name, ip, ok in results:
            status = "✅" if ok else "❌"
            self.app._log_message(f"   {status} [{name}] {ip}")

    def _browse_directory(self):
        d = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if d:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, d)
            self.app._save_ui_settings()

    def _browse_file(self):
        f = filedialog.askopenfilename(title="X3로 전송할 파일 선택", filetypes=[("eBook files", "*.epub;*.pdf;*.txt;*.mobi"), ("All files", "*.*")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)

    def _open_output_folder(self):
        folder = self.dir_entry.get().strip() or "./output"
        folder = os.path.abspath(folder)
        os.makedirs(folder, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("오류", f"폴더를 열 수 없습니다: {e}")

    def _direct_upload(self):
        file_path = self.file_entry.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("경고", "올바른 파일 경로를 지정해 주세요.")
            return
        self.app._save_ui_settings()
        self.app._log_message(f"📡 로컬 파일 직접 전송 중: {os.path.basename(file_path)}")
        self.direct_upload_btn.config(state="disabled")

        def task():
            results = self.app._make_uploader().upload_to_targets(file_path)
            self.master.after(0, lambda: self._direct_upload_finished(results, file_path))

        threading.Thread(target=task, daemon=True).start()

    def _direct_upload_finished(self, results: dict, file_path: str):
        if not self.app._sync_busy:
            self.direct_upload_btn.config(state="normal")
        all_ok, any_ok, summary = self.app._summarize_upload_results(results)
        basename = os.path.basename(file_path)
        if all_ok:
            self.app._log_message(f"🎉 파일 전송 성공 ({basename}): {summary}")
            from websync.integrations.notifier import ToastNotifier
            ToastNotifier.show_toast("파일 업로드 성공", f"'{basename}' 전송 완료.")
            messagebox.showinfo("완료", f"모든 기기로 전송 완료.\n{summary}")
        elif any_ok:
            self.app._log_message(f"⚠️ 파일 부분 전송 ({basename}): {summary}")
            from websync.integrations.notifier import ToastNotifier
            ToastNotifier.show_toast("파일 부분 업로드", summary, is_error=True)
            messagebox.showwarning("부분 성공", f"일부 기기만 전송되었습니다.\n{summary}")
        else:
            self.app._log_message(f"❌ 파일 전송 실패 ({basename}): {summary}")
            from websync.integrations.notifier import ToastNotifier
            ToastNotifier.show_toast("파일 업로드 실패", "기기 전송 오류. 연결 상태 확인 요망.", is_error=True)
            messagebox.showerror("오류", "기기로 전송하지 못했습니다.")

    # ------------------------------------------------------------------
    # 스케줄러
    # ------------------------------------------------------------------

