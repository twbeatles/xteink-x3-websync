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


class SyncPreviewMixin:
    def open_preview_window(self):
        """프리뷰 실행 후 결과를 새 윈도우에 체크박스와 함께 표시합니다."""
        self.app._log_message("\n🔍 프리뷰 스크래핑을 실행합니다...")
        self.app._set_sync_ui_busy(True)
        self.app.bottom_bar.progress_bar["value"] = 0

        def run():
            log_cb = self.app._make_log_callback()
            prog_cb = self.app._make_progress_callback()
            self._preview_data = self.service.preview_articles(log_callback=log_cb, progress_callback=prog_cb)
            
            self.master.after(0, self._show_preview_results)

        threading.Thread(target=run, daemon=True).start()

    def _show_preview_results(self):
        self.app._set_sync_ui_busy(False)
        self.app.bottom_bar.progress_bar["value"] = 0
        self.app._log_message("🔍 프리뷰 스크래핑이 완료되었습니다.\n")

        if not self._preview_data:
            messagebox.showinfo("프리뷰 결과", "수집된 새로운 기사가 없습니다.")
            return

        dialog = tk.Toplevel(self.app.root)
        dialog.title("기사 프리뷰 및 선택 전송")
        dialog.geometry("700x500")
        setup_dialog(dialog, self.app.root, 700, 500)

        # 안내
        lbl = ttk.Label(dialog, text="수집된 신규 기사 중 전송할 기사를 선택한 뒤 아래 버튼을 누르세요.")
        lbl.pack(fill="x", padx=15, pady=10)

        # 테이블
        columns = ("selected", "site", "title", "url")
        tree = create_scrolled_tree(dialog, columns, height=12)
        tree.heading("selected", text="선택")
        tree.heading("site", text="사이트")
        tree.heading("title", text="기사 제목")
        tree.heading("url", text="URL")
        
        tree.column("selected", width=50, anchor="center")
        tree.column("site", width=120, anchor="w")
        tree.column("title", width=320, anchor="w")
        tree.column("url", width=180, anchor="w")

        # 체크 상태 저장
        checked_state = {i: True for i in range(len(self._preview_data))}

        def refresh_tree():
            for item in tree.get_children():
                tree.delete(item)
            for idx, art in enumerate(self._preview_data):
                chk = "☑" if checked_state[idx] else "☐"
                tree.insert("", "end", iid=str(idx), values=(
                    chk, art["site_name"], art["title"], art["url"]
                ))

        refresh_tree()

        # 체크 클릭 핸들링
        def on_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            idx = int(item)
            checked_state[idx] = not checked_state[idx]
            refresh_tree()

        tree.bind("<Button-1>", on_click)

        # 전체 토글
        def toggle_all():
            val = not all(checked_state.values())
            for k in checked_state:
                checked_state[k] = val
            refresh_tree()

        # 동기화 실행
        def run_selected_sync():
            selected_arts = [self._preview_data[i] for i, checked in checked_state.items() if checked]
            if not selected_arts:
                messagebox.showwarning("선택 누락", "전송할 기사를 최소 하나 이상 선택해 주세요.", parent=dialog)
                return
            
            dialog.destroy()
            self._run_selected_sync_task(selected_arts)

        btn_bar = ttk.Frame(dialog)
        btn_bar.pack(fill="x", side="bottom", pady=10, padx=15)
        
        ttk.Button(btn_bar, text="전체 선택/해제", command=toggle_all).pack(side="left")
        ttk.Button(btn_bar, text="취소", command=dialog.destroy).pack(side="right", padx=5)
        ttk.Button(btn_bar, text="★ 선택 기사 기기로 전송", command=run_selected_sync).pack(side="right")

    def _run_selected_sync_task(self, selected_articles):
        if self.service.is_pipeline_running():
            messagebox.showwarning("실행 제한", "현재 다른 동기화 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.")
            return

        self.app._set_sync_ui_busy(True)
        self.app.bottom_bar.progress_bar["value"] = 0
        self.app._log_message(f"\n=== 선택 기사 {len(selected_articles)}건 동기화 실행 ===")

        def task():
            log_cb = self.app._make_log_callback()
            prog_cb = self.app._make_progress_callback()
            self.service.sync_selected_articles(selected_articles, log_callback=log_cb, progress_callback=prog_cb)
            self.master.after(0, self.app._sync_finished_ui)

        threading.Thread(target=task, daemon=True).start()

