"""첫 실행 공유 데이터 폴더 연결 마법사 (CustomTkinter 기반 모달)."""
from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk
from typing import TYPE_CHECKING, Callable, Optional

from websync.backup.format import MANIFEST_FILENAME, SITES_FILENAME
from websync.backup.portable_cfg import apply_portable_cfg, get_portable_cfg
from websync.gui.widgets import (
    CardFrame, COLOR_CARD_BG, COLOR_FG, COLOR_SECONDARY_FG, COLOR_ACCENT, get_font, setup_dialog
)

if TYPE_CHECKING:
    from websync.pipeline.service import SyncService


def should_show_portable_wizard(config: dict) -> bool:
    """마법사 표시 여부."""
    pd = get_portable_cfg(config)
    if pd.get("wizard_completed"):
        return False
    # 이미 폴더가 설정·활성화되어 있으면 스킵
    if pd.get("enabled") and (pd.get("folder") or "").strip():
        return False
    return True


class PortableDataWizard:
    """공유 데이터 폴더 연결/생성 또는 이 PC만 사용 모달 마법사."""

    def __init__(
        self,
        parent: ctk.CTk,
        service: "SyncService",
        *,
        on_done: Optional[Callable[[], None]] = None,
    ):
        self.parent = parent
        self.service = service
        self.on_done = on_done
        self.result: str | None = None  # local | connect | create | None

        self.dialog = ctk.CTkToplevel(parent)
        self.dialog.title("공유 데이터 폴더 설정")
        self.dialog.transient(parent)
        setup_dialog(self.dialog, parent, 580, 420)
        self.dialog.protocol("WM_DELETE_WINDOW", self._on_local_only)

        outer = ctk.CTkFrame(self.dialog, fg_color="transparent")
        outer.pack(fill="both", expand=True, padx=18, pady=18)

        ctk.CTkLabel(
            outer,
            text="PC를 바꿔도 사이트 목록과 전송 이력을 유지할까요?",
            font=get_font(15, "bold"),
            text_color=COLOR_FG,
        ).pack(anchor="w", pady=(0, 8))

        ctk.CTkLabel(
            outer,
            text="OneDrive·Google Drive 등 동기화되는 폴더를 지정하면\n"
                 "구독 사이트와 ‘이미 보낸 글’ 이력이 여러 PC에서 공유됩니다.\n"
                 "동기화 시 새 글만 전송할 수 있습니다.",
            font=get_font(12),
            text_color=COLOR_SECONDARY_FG,
            justify="left",
        ).pack(anchor="w", pady=(0, 14))

        btn_card = CardFrame(outer)
        btn_card.pack(fill="x", pady=6)

        ctk.CTkButton(
            btn_card,
            text="기존 공유 폴더 연결…",
            font=get_font(13, "bold"),
            fg_color=COLOR_ACCENT[0],
            hover_color=COLOR_ACCENT[1],
            height=38,
            command=self._connect_existing,
        ).pack(fill="x", padx=12, pady=(10, 4))

        ctk.CTkButton(
            btn_card,
            text="새 공유 폴더 만들기…",
            font=get_font(13),
            height=38,
            command=self._create_new,
        ).pack(fill="x", padx=12, pady=4)

        ctk.CTkButton(
            btn_card,
            text="이 PC만 사용 (나중에 설정)",
            font=get_font(13),
            fg_color=("#e9ecef", "#343a40"),
            text_color=COLOR_FG,
            height=38,
            command=self._on_local_only,
        ).pack(fill="x", padx=12, pady=(4, 10))

        ctk.CTkLabel(
            outer,
            text="나중에 고급 설정 → 공유 데이터 폴더에서도 변경할 수 있습니다.",
            font=get_font(12),
            text_color=COLOR_SECONDARY_FG,
        ).pack(anchor="w", pady=(12, 0))

    def show(self) -> None:
        self.dialog.wait_window()

    def _finish(self, result: str) -> None:
        self.result = result
        try:
            self.dialog.grab_release()
        except Exception:
            pass
        self.dialog.destroy()
        if self.on_done:
            try:
                self.on_done()
            except Exception:
                pass

    def _mark_wizard_done(self, **portable_updates) -> bool:
        config = self.service.config
        updates = {"wizard_completed": True, **portable_updates}
        apply_portable_cfg(config, updates)
        try:
            self.service.config_manager.save_config(config)
            self.service._reload_config()
            return True
        except Exception as e:
            messagebox.showerror("저장 실패", str(e), parent=self.dialog)
            return False

    def _on_local_only(self) -> None:
        if not self._mark_wizard_done(enabled=False):
            return
        self._finish("local")

    def _connect_existing(self) -> None:
        path = filedialog.askdirectory(
            parent=self.dialog,
            title="기존 공유 데이터 폴더 선택",
        )
        if not path:
            return
        sites = os.path.join(path, SITES_FILENAME)
        manifest = os.path.join(path, MANIFEST_FILENAME)
        if not (os.path.isfile(sites) or os.path.isfile(manifest)):
            if not messagebox.askyesno(
                "폴더 확인",
                f"선택한 폴더에 {SITES_FILENAME} / {manifest} 가 없습니다.\n"
                "그래도 이 폴더를 연결할까요?\n(이후 「지금 동기화」로 내보낼 수 있습니다)",
                parent=self.dialog,
            ):
                return

        if not self._mark_wizard_done(
            enabled=True,
            folder=path,
            auto_import_on_start=True,
            auto_export=True,
            include_history=True,
        ):
            return

        try:
            result = self.service.maybe_backup_pull(force=True)
            msg = result.get("message") or "가져오기 완료"
            if result.get("ok") or result.get("skipped"):
                messagebox.showinfo("연결 완료", f"공유 폴더를 연결했습니다.\n{msg}", parent=self.parent)
            else:
                messagebox.showwarning(
                    "연결됨 (가져오기 주의)",
                    f"폴더는 연결되었지만 가져오기에 문제가 있을 수 있습니다.\n{msg}",
                    parent=self.parent,
                )
        except Exception as e:
            messagebox.showwarning("연결됨", f"폴더는 저장되었습니다.\n가져오기: {e}", parent=self.parent)
        self._finish("connect")

    def _create_new(self) -> None:
        path = filedialog.askdirectory(
            parent=self.dialog,
            title="새 공유 데이터 폴더 선택 (비어 있거나 전용 폴더)",
        )
        if not path:
            return
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            messagebox.showerror("오류", f"폴더를 만들 수 없습니다:\n{e}", parent=self.dialog)
            return

        if not self._mark_wizard_done(
            enabled=True,
            folder=path,
            auto_import_on_start=True,
            auto_export=True,
            include_history=True,
        ):
            return

        try:
            result = self.service.maybe_backup_push(force=True)
            msg = result.get("message") or "내보내기 완료"
            if result.get("ok"):
                messagebox.showinfo(
                    "생성 완료",
                    f"공유 데이터 폴더를 만들고 현재 사이트·이력을 내보냈습니다.\n{msg}",
                    parent=self.parent,
                )
            else:
                messagebox.showwarning(
                    "폴더 설정됨",
                    f"폴더는 설정되었지만 내보내기에 실패했을 수 있습니다.\n{msg}",
                    parent=self.parent,
                )
        except Exception as e:
            messagebox.showwarning("폴더 설정됨", f"폴더는 저장되었습니다.\n내보내기: {e}", parent=self.parent)
        self._finish("create")
