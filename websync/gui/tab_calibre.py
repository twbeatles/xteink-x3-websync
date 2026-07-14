"""Calibre 서재 연동 탭 컴포넌트"""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from websync.gui.widgets import (
    create_scrollable_frame, create_scrolled_tree
)
from websync.integrations.notifier import ToastNotifier


class CalibreTab(ttk.Frame):
    """Calibre 서재 조회를 담당하는 탭"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.service = app.service
        self.calibre = app.calibre

        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        calibre_top_frame = ttk.LabelFrame(body, text=" Calibre 연동 설정 ")
        calibre_top_frame.pack(fill="x", padx=15, pady=10)
        calibre_top_frame.columnconfigure(1, weight=1)

        ttk.Label(calibre_top_frame, text="calibredb.exe 경로:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.calibre_entry = ttk.Entry(calibre_top_frame)
        self.calibre_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(calibre_top_frame, text="찾아보기", command=self._browse_calibredb).grid(row=0, column=2, padx=5, pady=8)
        self.calibre_conn_btn = ttk.Button(calibre_top_frame, text="연결 확인 & 서재 로드", command=self._test_and_load_calibre)
        self.calibre_conn_btn.grid(row=0, column=3, padx=10, pady=8)
        self.app._bind_autosave(self.calibre_entry)

        ttk.Label(calibre_top_frame, text="라이브러리 경로 (선택):").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.calibre_lib_entry = ttk.Entry(calibre_top_frame)
        self.calibre_lib_entry.grid(row=1, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(calibre_top_frame, text="폴더 선택", command=self._browse_calibre_library).grid(row=1, column=2, padx=5, pady=8)
        ttk.Label(
            calibre_top_frame,
            text="비워두면 Calibre 기본 라이브러리 사용",
            font=("Malgun Gothic", 8),
            foreground=self.app.style.lookup(".", "foreground") if hasattr(self.app, "style") else "#6c757d",
        ).grid(row=1, column=3, padx=10, pady=8, sticky="w")
        self.app._bind_autosave(self.calibre_lib_entry)

        calibre_list_frame = ttk.LabelFrame(body, text=" 내 Calibre 서재 도서 목록 ")
        calibre_list_frame.pack(fill="x", padx=15, pady=5)

        c_columns = ("id", "title", "authors", "formats")
        self.calibre_tree = create_scrolled_tree(
            calibre_list_frame, c_columns, height=8, padx=10, pady=10
        )
        self.calibre_tree.heading("id", text="ID")
        self.calibre_tree.heading("title", text="도서 제목")
        self.calibre_tree.heading("authors", text="저자")
        self.calibre_tree.heading("formats", text="보유 포맷")
        self.calibre_tree.column("id", width=50, minwidth=40, anchor="center")
        self.calibre_tree.column("title", width=320, minwidth=120, anchor="w")
        self.calibre_tree.column("authors", width=180, minwidth=80, anchor="w")
        self.calibre_tree.column("formats", width=120, minwidth=80, anchor="center")

        calibre_action_frame = ttk.Frame(body)
        calibre_action_frame.pack(fill="x", padx=15, pady=10)
        self.calibre_send_btn = ttk.Button(calibre_action_frame, text="★ 선택한 도서 X3 기기로 즉시 전송 (다중 선택 가능)", command=self._send_calibre_books)
        self.calibre_send_btn.pack(fill="x", pady=5)

    def _browse_calibredb(self):
        from tkinter import filedialog
        f = filedialog.askopenfilename(title="calibredb.exe 실행파일 찾기", filetypes=[("Executable", "calibredb.exe"), ("All files", "*.*")])
        if f:
            self.calibre_entry.delete(0, tk.END)
            self.calibre_entry.insert(0, f)
            self.app._save_ui_settings()

    def _browse_calibre_library(self):
        from tkinter import filedialog
        d = filedialog.askdirectory(title="Calibre 라이브러리 폴더 선택 (metadata.db가 있는 폴더)")
        if d:
            self.calibre_lib_entry.delete(0, tk.END)
            self.calibre_lib_entry.insert(0, d)
            self.app._save_ui_settings()

    def _test_and_load_calibre(self, silent=False):
        self.app._save_ui_settings()
        self.calibre.calibre_path = self.calibre_entry.get().strip()
        self.calibre.library_path = self.calibre_lib_entry.get().strip()
        if not silent:
            self.app._log_message("📚 Calibre 연결 확인 중...")
            self.calibre_conn_btn.config(state="disabled")
        if not self.calibre.test_connection():
            if not silent:
                self.app._log_message("❌ Calibre 연동 실패: 경로를 확인하세요.")
                messagebox.showerror("Calibre 연동 실패", "calibredb.exe 경로를 찾지 못했습니다.")
                if not self.app._sync_busy:
                    self.calibre_conn_btn.config(state="normal")
            return
        def worker():
            books = self.calibre.list_books()
            self.master.after(0, lambda: self._show_calibre_books(books, silent))

        threading.Thread(target=worker, daemon=True).start()

    def _show_calibre_books(self, books: list, silent: bool):
        if not self.app._sync_busy:
            self.calibre_conn_btn.config(state="normal")
        for item in self.calibre_tree.get_children():
            self.calibre_tree.delete(item)
        if not books:
            if not silent:
                self.app._log_message("⚠️ Calibre 연동 성공했으나 책이 없습니다.")
            return
        for bk in books:
            formats = bk.get("formats", "")
            formats_str = ", ".join(formats) if isinstance(formats, list) else str(formats)
            self.calibre_tree.insert("", "end", iid=str(bk.get("id")), values=(bk.get("id"), bk.get("title"), bk.get("authors", ""), formats_str))
        if not silent:
            self.app._log_message(f"🎉 Calibre 서재 로드 완료: {len(books)}권")
            ToastNotifier.show_toast("Calibre 연동 성공", f"서재에서 {len(books)}권 불러왔습니다.")

    def _send_calibre_books(self):
        selected_items = self.calibre_tree.selection()
        if not selected_items:
            messagebox.showwarning("선택 누락", "전송할 도서를 선택해 주세요.")
            return
        self.app._save_ui_settings()
        self.calibre_send_btn.config(state="disabled")
        self.app._log_message(f"\n=== Calibre 책 {len(selected_items)}권 무선 전송 시작 ===")

        def task():
            success_cnt = 0
            uploader = self.app._make_uploader()
            for item_id in selected_items:
                book_id = int(item_id)
                file_path = self.calibre.get_book_file_path(book_id)
                if not file_path or not os.path.exists(file_path):
                    self.master.after(0, lambda b=book_id: self.app._log_message(f"❌ [책 ID {b}] 파일 경로 조회 실패"))
                    continue
                self.master.after(0, lambda p=file_path: self.app._log_message(f"📡 전송 중: {os.path.basename(p)}"))
                results = uploader.upload_to_targets(file_path)
                all_ok, any_ok, summary = self.app._summarize_upload_results(results)
                if all_ok:
                    self.master.after(0, lambda p=file_path, s=summary: self.app._log_message(f"🎉 성공: {os.path.basename(p)} ({s})"))
                    success_cnt += 1
                elif any_ok:
                    self.master.after(0, lambda p=file_path, s=summary: self.app._log_message(f"⚠️ 부분 성공: {os.path.basename(p)} ({s})"))
                    success_cnt += 1
                else:
                    self.master.after(0, lambda p=file_path, s=summary: self.app._log_message(f"❌ 실패: {os.path.basename(p)} ({s})"))
            self.master.after(0, lambda: self._calibre_send_finished(success_cnt, len(selected_items)))

        threading.Thread(target=task, daemon=True).start()

    def _calibre_send_finished(self, success_cnt: int, total_cnt: int):
        if not self.app._sync_busy:
            self.calibre_send_btn.config(state="normal")
        self.app._log_message(f"=== Calibre 도서 전송 종료: {success_cnt}/{total_cnt} 성공 ===\n")
        if success_cnt > 0:
            ToastNotifier.show_toast("Calibre 도서 동기화", f"{success_cnt}권 전송 완료.")
            messagebox.showinfo("완료", f"{success_cnt}권의 책이 전송되었습니다.")
        else:
            messagebox.showerror("오류", "전송에 실패했습니다. 기기 연결 상태를 확인하세요.")
