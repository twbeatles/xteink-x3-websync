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


class DeviceFilesActionsMixin:
    def _delete_selected(self) -> None:
        if self._busy:
            return
        items = self._selected_items()
        if not items:
            messagebox.showwarning("경고", "삭제할 항목을 선택해 주세요.")
            return
        names = ", ".join(i.get("name", "") for i in items[:5])
        if len(items) > 5:
            names += f" 외 {len(items) - 5}개"
        if not messagebox.askyesno(
            "삭제 확인",
            f"{len(items)}개 항목을 기기에서 삭제합니다.\n\n{names}\n\n"
            "이 작업은 되돌릴 수 없습니다. (PC 동기화 이력은 유지됩니다)\n계속할까요?",
        ):
            return

        ip = self._selected_ip()
        paths = [i["path"] for i in items]
        self._set_busy(True)
        self.app._log_message(f"🗑 [{ip}] 삭제 요청: {len(paths)}개")

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

    def _delete_finished(self, ip: str, count: int, err: str | None) -> None:
        self._set_busy(False)
        if err:
            self.app._log_message(f"❌ [{ip}] 삭제 실패: {err}")
            messagebox.showerror(
                "삭제 실패",
                f"{err}\n\n비어 있지 않은 폴더이거나 보호된 경로일 수 있습니다.",
            )
            return
        self.app._log_message(f"✅ [{ip}] {count}개 삭제 완료")
        self.refresh()

    def _mkdir(self) -> None:
        if self._busy:
            return
        ip = self._selected_ip()
        if not ip:
            messagebox.showwarning("경고", "기기를 선택해 주세요.")
            return
        name = simpledialog.askstring("폴더 생성", "새 폴더 이름:", parent=self.app.root)
        if not name:
            return
        name = name.strip()
        if not name or "/" in name or "\\" in name:
            messagebox.showerror("오류", "올바른 폴더 이름을 입력해 주세요.")
            return

        path = self._current_path
        self._set_busy(True)
        self.app._log_message(f"📂 [{ip}] 폴더 생성: {path}/{name}")

        def task():
            err: str | None = None
            try:
                self._make_client().mkdir(name, path=path, ip=ip)
            except DeviceClientError as e:
                err = str(e)
            self.app.root.after(
                0, lambda ip=ip, name=name, err=err: self._mkdir_finished(ip, name, err)
            )

        threading.Thread(target=task, daemon=True).start()

    def _mkdir_finished(self, ip: str, name: str, err: str | None) -> None:
        self._set_busy(False)
        if err:
            self.app._log_message(f"❌ [{ip}] 폴더 생성 실패: {err}")
            messagebox.showerror("폴더 생성 실패", err)
            return
        self.app._log_message(f"✅ [{ip}] 폴더 생성됨: {name}")
        self.refresh()

    def _rename_selected(self) -> None:
        if self._busy:
            return
        items = self._selected_items()
        if len(items) != 1:
            messagebox.showwarning("경고", "이름을 변경할 파일 하나를 선택해 주세요.")
            return
        item = items[0]
        if item.get("isDirectory"):
            messagebox.showwarning(
                "경고", "폴더 이름 변경은 기기 API에서 지원하지 않습니다. (파일만 가능)"
            )
            return
        new_name = simpledialog.askstring(
            "이름 변경",
            "새 파일 이름:",
            initialvalue=item.get("name", ""),
            parent=self.app.root,
        )
        if not new_name or new_name.strip() == item.get("name"):
            return
        new_name = new_name.strip()
        if "/" in new_name or "\\" in new_name:
            messagebox.showerror("오류", "이름에 경로 구분자를 넣을 수 없습니다.")
            return

        ip = self._selected_ip()
        self._set_busy(True)
        self.app._log_message(f"✏ [{ip}] 이름 변경: {item['path']} → {new_name}")

        def task():
            err: str | None = None
            try:
                self._make_client().rename(item["path"], new_name, ip=ip)
            except DeviceClientError as e:
                err = str(e)
            self.app.root.after(
                0, lambda ip=ip, err=err: self._op_finished(ip, "이름 변경", err)
            )

        threading.Thread(target=task, daemon=True).start()

    def _move_selected(self) -> None:
        if self._busy:
            return
        items = [i for i in self._selected_items() if not i.get("isDirectory")]
        if not items:
            messagebox.showwarning(
                "경고", "이동할 파일을 선택해 주세요. (폴더는 이동 API 미지원)"
            )
            return
        dest = simpledialog.askstring(
            "파일 이동",
            "대상 폴더 경로 (예: /Books 또는 /Read):",
            initialvalue="/",
            parent=self.app.root,
        )
        if dest is None:
            return
        dest = normalize_remote_path(dest)
        ip = self._selected_ip()
        self._set_busy(True)
        self.app._log_message(f"➡ [{ip}] {len(items)}개 → {dest}")

        def task():
            client = self._make_client()
            ok = 0
            errors: list[str] = []
            for item in items:
                try:
                    client.move(item["path"], dest, ip=ip)
                    ok += 1
                except DeviceClientError as e:
                    errors.append(f"{item.get('name')}: {e}")
            self.app.root.after(
                0,
                lambda ip=ip, ok=ok, errors=errors: self._multi_op_finished(
                    ip, "이동", ok, errors
                ),
            )

        threading.Thread(target=task, daemon=True).start()

    def _op_finished(self, ip: str, label: str, err: str | None) -> None:
        self._set_busy(False)
        if err:
            self.app._log_message(f"❌ [{ip}] {label} 실패: {err}")
            messagebox.showerror(f"{label} 실패", err)
            return
        self.app._log_message(f"✅ [{ip}] {label} 완료")
        self.refresh()

    def _multi_op_finished(
        self, ip: str, label: str, ok: int, errors: list[str]
    ) -> None:
        self._set_busy(False)
        if errors:
            self.app._log_message(
                f"⚠️ [{ip}] {label} 부분 실패: 성공 {ok}, 실패 {len(errors)}"
            )
            messagebox.showwarning(
                f"{label} 결과",
                f"성공 {ok}개, 실패 {len(errors)}개\n\n" + "\n".join(errors[:8]),
            )
        else:
            self.app._log_message(f"✅ [{ip}] {label} 완료: {ok}개")
        self.refresh()

    # ------------------------------------------------------------------
    # 다운로드 / 업로드
    # ------------------------------------------------------------------

    def _download_selected(self) -> None:
        if self._busy:
            return
        items = [i for i in self._selected_items() if not i.get("isDirectory")]
        if not items:
            messagebox.showwarning(
                "경고", "다운로드할 파일을 선택해 주세요. (폴더는 지원하지 않습니다)"
            )
            return

        dest_dir = filedialog.askdirectory(title="저장할 PC 폴더 선택")
        if not dest_dir:
            return

        ip = self._selected_ip()
        self._set_busy(True)
        self.app._log_message(f"⬇ [{ip}] 다운로드 시작: {len(items)}개 → {dest_dir}")

        def task():
            client = self._make_client()
            ok = 0
            errors: list[str] = []
            for item in items:
                local = os.path.join(dest_dir, item["name"])
                try:
                    client.download(item["path"], local, ip=ip)
                    ok += 1
                except DeviceClientError as e:
                    errors.append(f"{item['name']}: {e}")
            self.app.root.after(
                0,
                lambda ip=ip, ok=ok, errors=errors: self._download_finished(ip, ok, errors),
            )

        threading.Thread(target=task, daemon=True).start()

    def _download_finished(self, ip: str, ok: int, errors: list[str]) -> None:
        self._set_busy(False)
        if errors:
            self.app._log_message(
                f"⚠️ [{ip}] 다운로드 부분 실패: 성공 {ok}, 실패 {len(errors)}"
            )
            messagebox.showwarning(
                "다운로드 결과",
                f"성공 {ok}개, 실패 {len(errors)}개\n\n" + "\n".join(errors[:8]),
            )
        else:
            self.app._log_message(f"✅ [{ip}] 다운로드 완료: {ok}개")
            messagebox.showinfo("다운로드 완료", f"{ok}개 파일을 저장했습니다.")

    def _upload_to_current(self) -> None:
        if self._busy:
            return
        ip = self._selected_ip()
        if not ip:
            messagebox.showwarning("경고", "기기를 선택해 주세요.")
            return
        paths = filedialog.askopenfilenames(
            title="기기로 업로드할 파일 선택",
            filetypes=[
                ("전자책/문서", "*.epub;*.pdf;*.mobi;*.txt"),
                ("모든 파일", "*.*"),
            ],
        )
        if not paths:
            return

        remote_dir = self._current_path
        client = self._make_client()
        uploader = X3Uploader(ip)
        warn = bool(self.warn_overwrite_var.get())

        # 덮어쓰기 경고 (선택 시)
        if warn:
            collisions = []
            try:
                for p in paths:
                    safe = uploader._sanitize_filename(p)
                    if client.remote_file_exists(remote_dir, safe, ip=ip):
                        collisions.append(safe)
            except DeviceClientError as e:
                if not messagebox.askyesno(
                    "확인",
                    f"기기 목록 확인 실패: {e}\n그래도 업로드를 시도할까요?",
                ):
                    return
            if collisions:
                if not messagebox.askyesno(
                    "덮어쓰기 경고",
                    "다음 파일이 이미 존재합니다 (업로드 시 덮어씀):\n\n"
                    + "\n".join(collisions[:12])
                    + ("\n…" if len(collisions) > 12 else "")
                    + "\n\n계속할까요?",
                ):
                    return

        self._set_busy(True)
        self.app._log_message(
            f"⬆ [{ip}] 업로드 {len(paths)}개 → {remote_dir}"
        )

        def task():
            ok = 0
            errors: list[str] = []
            c = self._make_client()
            for p in paths:
                try:
                    c.upload_to_path(p, remote_dir=remote_dir, ip=ip)
                    ok += 1
                except DeviceClientError as e:
                    errors.append(f"{os.path.basename(p)}: {e}")
            self.app.root.after(
                0,
                lambda ip=ip, ok=ok, errors=errors: self._multi_op_finished(
                    ip, "업로드", ok, errors
                ),
            )

        threading.Thread(target=task, daemon=True).start()

    # ------------------------------------------------------------------
    # 오래된 동기화 EPUB 정리
    # ------------------------------------------------------------------

