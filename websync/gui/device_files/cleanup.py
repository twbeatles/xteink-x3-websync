from __future__ import annotations

import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog

from websync.gui.widgets import (
    HINT_COLOR,
    YELLOW_COLOR,
    GREEN_COLOR,
    RED_COLOR,
    create_scrollable_frame,
    create_scrolled_tree,
)
from websync.upload.device_client import (
    X3DeviceClient,
    DeviceClientError,
    normalize_remote_path,
    parent_remote_path,
    format_file_size,
    filter_old_sync_epubs,
)
from websync.upload.uploader import X3Uploader, normalize_upload_remote_dir


class DeviceFilesCleanupMixin:
    def _old_candidates(self) -> list[dict]:
        days = self._cleanup_days()
        return filter_old_sync_epubs(self._all_items, days)

    def _select_old_sync_epubs(self) -> None:
        candidates = self._old_candidates()
        if not candidates:
            messagebox.showinfo(
                "후보 없음",
                f"현재 폴더에서 {self._cleanup_days()}일보다 오래된 "
                "동기화 EPUB(파일명 날짜 기준)이 없습니다.",
            )
            return
        # 필터 해제 후 트리에서 선택
        self.filter_var.set("")
        self.epub_only_var.set(False)
        self._apply_filter_to_tree()
        self.file_tree.selection_remove(self.file_tree.selection())
        path_set = {c["path"] for c in candidates}
        to_select = []
        for iid, item in self._items_by_iid.items():
            if item.get("path") in path_set:
                to_select.append(iid)
        if to_select:
            self.file_tree.selection_set(to_select)
            self.file_tree.see(to_select[0])
        self.app._log_message(
            f"🧹 오래된 EPUB 후보 {len(candidates)}개 선택 ({self._cleanup_days()}일+)"
        )

    def _cleanup_old_sync_epubs(self) -> None:
        if self._busy:
            return
        candidates = self._old_candidates()
        if not candidates:
            messagebox.showinfo(
                "후보 없음",
                f"현재 폴더에서 {self._cleanup_days()}일보다 오래된 동기화 EPUB이 없습니다.",
            )
            return
        preview = "\n".join(
            f"· {c.get('name')} ({c.get('sync_date', '?')})" for c in candidates[:15]
        )
        if len(candidates) > 15:
            preview += f"\n… 외 {len(candidates) - 15}개"
        if not messagebox.askyesno(
            "오래된 EPUB 삭제",
            f"{self._cleanup_days()}일보다 오래된 동기화 EPUB {len(candidates)}개를 "
            f"기기에서 삭제합니다.\n\n{preview}\n\n"
            "PC 동기화 이력은 유지됩니다. 계속할까요?",
        ):
            return

        # 설정 일수 저장
        self._save_device_files_settings()

        ip = self._selected_ip()
        paths = [c["path"] for c in candidates]
        self._set_busy(True)
        self.app._log_message(f"🧹 [{ip}] 오래된 EPUB 삭제: {len(paths)}개")

        def task():
            err: str | None = None
            try:
                self._make_client().delete_paths(paths, ip=ip)
            except DeviceClientError as e:
                err = str(e)
            self.app.root.after(
                0, lambda ip=ip, count=len(paths), err=err: self._delete_finished(ip, count, err)
            )

        threading.Thread(target=task, daemon=True).start()

