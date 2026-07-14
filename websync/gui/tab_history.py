"""동기화 이력 탭 컴포넌트"""
import hashlib
import tkinter as tk
from tkinter import ttk, messagebox

from websync.gui.widgets import (
    YELLOW_COLOR, create_scrollable_frame, create_scrolled_tree
)
from websync.db.history import SyncHistoryDbError


class HistoryTab(ttk.Frame):
    """동기화 이력 조회를 담당하는 탭"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.service = app.service
        self.db = app.service.db
        
        self._history_url_by_iid: dict[str, str] = {}
        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        ctrl_frame = ttk.Frame(body)
        ctrl_frame.pack(fill="x", padx=15, pady=8)

        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="🔄 이력 새로고침", command=self._refresh_history).pack(side="left", padx=3)
        ttk.Button(btn_row, text="🗑 선택 항목 삭제 (재전송 허용)", command=self._delete_history_entry).pack(side="left", padx=3)
        ttk.Button(btn_row, text="⚠️ 전체 이력 초기화", command=self._clear_all_history).pack(side="left", padx=3)

        self.history_count_label = ttk.Label(ctrl_frame, text="", foreground=YELLOW_COLOR)
        self.history_count_label.pack(anchor="e", padx=10, pady=(4, 0))

        hist_frame = ttk.LabelFrame(body, text=" 전송 완료된 포스트 목록 (최신 200건) ")
        hist_frame.pack(fill="x", padx=15, pady=5)

        h_columns = ("site", "title", "synced_at", "url")
        self.hist_tree = create_scrolled_tree(
            hist_frame, h_columns, height=10, selectmode="extended"
        )
        self.hist_tree.heading("site", text="사이트")
        self.hist_tree.heading("title", text="제목")
        self.hist_tree.heading("synced_at", text="전송 시각")
        self.hist_tree.heading("url", text="URL")
        self.hist_tree.column("site", width=120, minwidth=80, anchor="w")
        self.hist_tree.column("title", width=280, minwidth=120, anchor="w")
        self.hist_tree.column("synced_at", width=150, minwidth=100, anchor="center")
        self.hist_tree.column("url", width=250, minwidth=120, anchor="w")
        self.hist_tree.bind("<Double-1>", self._on_history_double_click)

    def _on_history_double_click(self, _event=None):
        selected = self.hist_tree.selection()
        if not selected:
            return
        url = self._history_url_by_iid.get(selected[0], "")
        if not url:
            return
        self.app.root.clipboard_clear()
        self.app.root.clipboard_append(url)
        self.app._log_message(f"📋 URL 복사됨: {url[:80]}{'...' if len(url) > 80 else ''}")

    def _refresh_history(self):
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        self._history_url_by_iid.clear()
        try:
            rows = self.db.get_history(limit=200)
            count = self.db.get_count()
        except SyncHistoryDbError as e:
            messagebox.showerror("이력 조회 실패", str(e))
            self.history_count_label.config(text="이력 조회 실패")
            return
        for row in rows:
            url = row[0]
            site_name = row[1] if len(row) > 1 else ""
            title = row[2] if len(row) > 2 else ""
            synced_at = row[3] if len(row) > 3 else ""
            devices = row[4] if len(row) > 4 else ""
            iid = hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:24]
            self._history_url_by_iid[iid] = url
            display_title = title or ""
            if devices:
                display_title = f"{display_title} [{devices}]" if display_title else f"[{devices}]"
            self.hist_tree.insert("", "end", iid=iid, values=(
                site_name or "", display_title, synced_at or "", url or ""
            ))
        self.history_count_label.config(text=f"총 {count}건 기록됨")

    def _delete_history_entry(self):
        selected = self.hist_tree.selection()
        if not selected:
            messagebox.showwarning("경고", "삭제할 항목을 선택해 주세요.")
            return
        if not messagebox.askyesno("확인", f"{len(selected)}개 항목을 삭제하면 다음 동기화 시 재수집됩니다. 계속할까요?"):
            return
        try:
            for iid in selected:
                url = self._history_url_by_iid.get(iid, iid)
                self.db.delete_entry(url)
        except SyncHistoryDbError as e:
            messagebox.showerror("이력 삭제 실패", str(e))
            self.app._log_message(f"❌ 이력 삭제 실패: {e}")
            return
        self._refresh_history()
        self.app._log_message(f"🗑 이력 {len(selected)}건 삭제 완료 (재전송 허용)")

    def _clear_all_history(self):
        if not messagebox.askyesno("전체 초기화 확인", "모든 동기화 이력을 삭제합니다.\n다음 동기화 시 모든 기사가 재수집됩니다. 계속할까요?"):
            return
        try:
            self.db.clear_all()
        except SyncHistoryDbError as e:
            messagebox.showerror("이력 초기화 실패", str(e))
            self.app._log_message(f"❌ 이력 초기화 실패: {e}")
            return
        self._refresh_history()
        self.app._log_message("⚠️ 동기화 이력 전체 초기화 완료")
