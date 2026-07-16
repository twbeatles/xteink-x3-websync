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


class DeviceFilesBrowserMixin:
    def _make_client(self) -> X3DeviceClient:
        config = self.service.config
        ip = (config.get("x3_ip") or "").strip()
        if not ip and hasattr(self.app, "tab_sync"):
            ip = self.app.tab_sync.ip_entry.get().strip()
        return X3DeviceClient(ip, config.get("x3_devices", []))

    def refresh_device_list(self) -> None:
        """설정에 등록된 기기 콤보 갱신."""
        client = self._make_client()
        targets = client._build_target_list()
        self._device_choices = [(f"{t['name']} ({t['ip']})", t["ip"]) for t in targets]
        labels = [label for label, _ in self._device_choices]
        prev_ip = self._selected_ip()
        self.device_cb["values"] = labels
        if not labels:
            self.device_cb.set("")
            self.status_label.config(text="등록된 기기 없음", foreground=RED_COLOR)
            return
        idx = 0
        if prev_ip:
            for i, (_, ip) in enumerate(self._device_choices):
                if ip == prev_ip:
                    idx = i
                    break
        self.device_cb.current(idx)

    def _selected_ip(self) -> str:
        sel = self.device_cb.get()
        for label, ip in self._device_choices:
            if label == sel:
                return ip
        if self._device_choices:
            return self._device_choices[0][1]
        return ""

    def _on_device_changed(self) -> None:
        df = self._device_files_conf()
        browse = normalize_remote_path(df.get("default_browse_path", "/"))
        self._current_path = browse
        self.path_var.set(browse)
        self.refresh()

    def _set_busy(self, busy: bool) -> None:
        self._busy = busy
        state = "disabled" if busy else "normal"
        for btn in self._action_buttons:
            btn.config(state=state)
        self.device_cb.config(state="disabled" if busy else "readonly")

    # ------------------------------------------------------------------
    # 목록 로드
    # ------------------------------------------------------------------

    def refresh(self) -> None:
        if self._busy:
            return
        self.refresh_device_list()
        ip = self._selected_ip()
        if not ip:
            messagebox.showwarning(
                "경고", "등록된 기기가 없습니다. 뉴스 동기화 탭에서 주소를 설정하세요."
            )
            return

        path = normalize_remote_path(self.path_var.get() or self._current_path)
        self._current_path = path
        self.path_var.set(path)
        self._set_busy(True)
        self.status_label.config(text="불러오는 중…", foreground=YELLOW_COLOR)
        self.app._log_message(f"📁 [{ip}] 파일 목록 요청: {path}")

        def task():
            client = self._make_client()
            status_text = ""
            status_ok = False
            err: str | None = None
            items: list[dict] = []
            try:
                try:
                    st = client.get_status(ip)
                    status_text = X3DeviceClient.format_status_summary(st)
                    status_ok = True
                except DeviceClientError as e:
                    status_text = f"상태 조회 실패 — {e}"
                items = client.list_files(path, ip=ip)
            except DeviceClientError as e:
                err = str(e)
            self.app.root.after(
                0,
                lambda ip=ip, path=path, items=items, status_text=status_text, status_ok=status_ok, err=err: self._refresh_finished(
                    ip, path, items, status_text, status_ok, err
                ),
            )

        threading.Thread(target=task, daemon=True).start()

    def _refresh_finished(
        self,
        ip: str,
        path: str,
        items: list[dict],
        status_text: str,
        status_ok: bool,
        err: str | None,
    ) -> None:
        self._set_busy(False)
        if err:
            self.status_label.config(text="연결 실패", foreground=RED_COLOR)
            self._all_items = []
            self._fill_tree([])
            self.summary_label.config(text="")
            self.app._log_message(f"❌ [{ip}] 파일 목록 실패: {err}")
            messagebox.showerror(
                "파일 목록 실패",
                f"기기({ip})에서 목록을 가져오지 못했습니다.\n\n"
                f"{err}\n\n"
                "기기가 File Transfer 모드인지, 같은 Wi-Fi인지 확인해 주세요.",
            )
            return

        self._current_path = path
        self.path_var.set(path)
        self._all_items = items
        self._apply_filter_to_tree()
        if status_ok:
            self.status_label.config(text=status_text, foreground=GREEN_COLOR)
        else:
            self.status_label.config(
                text=status_text or "연결됨(상태 미지원)", foreground=YELLOW_COLOR
            )
        self.app._log_message(f"✅ [{ip}] {path} — {len(items)}개 항목")

    def _apply_filter_to_tree(self) -> None:
        q = (self.filter_var.get() or "").strip().lower()
        epub_only = self.epub_only_var.get()
        filtered: list[dict] = []
        for item in self._all_items:
            if epub_only and not item.get("isDirectory") and not item.get("isEpub"):
                continue
            if q and q not in (item.get("name") or "").lower():
                continue
            filtered.append(item)
        self._fill_tree(filtered)

        file_count = sum(1 for i in filtered if not i.get("isDirectory"))
        dir_count = sum(1 for i in filtered if i.get("isDirectory"))
        total_size = sum(int(i.get("size") or 0) for i in filtered if not i.get("isDirectory"))
        self.summary_label.config(
            text=f"폴더 {dir_count} · 파일 {file_count} · {format_file_size(total_size)}"
        )

    def _fill_tree(self, items: list[dict]) -> None:
        for child in self.file_tree.get_children():
            self.file_tree.delete(child)
        self._items_by_iid.clear()
        for idx, item in enumerate(items):
            iid = str(idx)
            self._items_by_iid[iid] = item
            if item.get("isDirectory"):
                kind = "📁 폴더"
                size_s = "-"
            elif item.get("isEpub"):
                kind = "📕 EPUB"
                size_s = format_file_size(item.get("size"))
            else:
                kind = "📄 파일"
                size_s = format_file_size(item.get("size"))
            self.file_tree.insert(
                "", "end", iid=iid, values=(kind, item.get("name", ""), size_s)
            )

    # ------------------------------------------------------------------
    # 탐색
    # ------------------------------------------------------------------

    def _go_to_path(self) -> None:
        self.path_var.set(normalize_remote_path(self.path_var.get()))
        self.refresh()

    def _go_parent(self) -> None:
        parent = parent_remote_path(self._current_path)
        self.path_var.set(parent)
        self.refresh()

    def _on_double_click(self, _event=None) -> None:
        selected = self.file_tree.selection()
        if not selected:
            return
        item = self._items_by_iid.get(selected[0])
        if not item:
            return
        if item.get("isDirectory"):
            self.path_var.set(item["path"])
            self.refresh()

    def _selected_items(self) -> list[dict]:
        result = []
        for iid in self.file_tree.selection():
            item = self._items_by_iid.get(iid)
            if item:
                result.append(item)
        return result

    def _cleanup_days(self) -> int:
        try:
            return max(1, int(self.cleanup_days_var.get()))
        except (TypeError, ValueError):
            return 14

    # ------------------------------------------------------------------
    # 삭제 / 폴더 / 이름변경 / 이동
    # ------------------------------------------------------------------

