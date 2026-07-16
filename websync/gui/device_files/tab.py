"""기기 SD 카드 파일 관리 탭 (조립)."""
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

from websync.gui.device_files.settings import DeviceFilesSettingsMixin
from websync.gui.device_files.browser import DeviceFilesBrowserMixin
from websync.gui.device_files.actions import DeviceFilesActionsMixin
from websync.gui.device_files.cleanup import DeviceFilesCleanupMixin


class DeviceFilesTab(
    DeviceFilesSettingsMixin,
    DeviceFilesBrowserMixin,
    DeviceFilesActionsMixin,
    DeviceFilesCleanupMixin,
    ttk.Frame,
):
    """등록된 X3 기기의 파일 목록·삭제·이름변경·이동·업로드·정리."""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.service = app.service

        self._current_path = "/"
        self._items_by_iid: dict[str, dict] = {}
        self._busy = False
        self._device_choices: list[tuple[str, str]] = []  # (label, ip)
        self._all_items: list[dict] = []

        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        hint = ttk.Label(
            body,
            text=(
                "기기가 File Transfer 또는 Calibre Wireless 모드일 때만 사용 가능합니다. "
                "삭제·덮어쓰기는 복구할 수 없습니다. 동기화 이력(PC DB)은 기본적으로 건드리지 않습니다."
            ),
            font=("Malgun Gothic", 8),
            foreground=HINT_COLOR,
            wraplength=820,
        )
        hint.pack(fill="x", padx=15, pady=(8, 4))

        # 상단: 기기 선택 + 상태 + 새로고침
        top = ttk.Frame(body)
        top.pack(fill="x", padx=15, pady=4)

        ttk.Label(top, text="기기:").pack(side="left", padx=(0, 4))
        self.device_cb = ttk.Combobox(top, state="readonly", width=36)
        self.device_cb.pack(side="left", padx=2)
        self.device_cb.bind("<<ComboboxSelected>>", lambda _e: self._on_device_changed())

        self.refresh_btn = ttk.Button(top, text="🔄 새로고침", command=self.refresh)
        self.refresh_btn.pack(side="left", padx=6)

        self.status_label = ttk.Label(top, text="미연결", foreground=YELLOW_COLOR)
        self.status_label.pack(side="left", padx=8)

        # 설정: 기본 업로드/탐색 경로
        settings_row = ttk.LabelFrame(body, text=" 전송·탐색 기본 경로 (동기화·직접 업로드 공통) ")
        settings_row.pack(fill="x", padx=15, pady=4)
        inner_s = ttk.Frame(settings_row)
        inner_s.pack(fill="x", padx=8, pady=6)

        ttk.Label(inner_s, text="기본 업로드 경로:").grid(row=0, column=0, sticky="w", padx=2)
        self.upload_path_var = tk.StringVar(value="/")
        self.upload_path_entry = ttk.Entry(inner_s, textvariable=self.upload_path_var, width=28)
        self.upload_path_entry.grid(row=0, column=1, sticky="w", padx=4)
        ttk.Button(inner_s, text="현재 경로로", command=self._set_upload_path_current).grid(
            row=0, column=2, padx=2
        )
        ttk.Button(inner_s, text="저장", command=self._save_device_files_settings).grid(
            row=0, column=3, padx=4
        )

        self.warn_overwrite_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            inner_s,
            text="수동 업로드 시 동일 이름 덮어쓰기 경고",
            variable=self.warn_overwrite_var,
            command=self._save_device_files_settings,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # 경로 바
        path_row = ttk.Frame(body)
        path_row.pack(fill="x", padx=15, pady=4)
        ttk.Label(path_row, text="경로:").pack(side="left")
        self.path_var = tk.StringVar(value="/")
        self.path_entry = ttk.Entry(path_row, textvariable=self.path_var)
        self.path_entry.pack(side="left", fill="x", expand=True, padx=6)
        self.path_entry.bind("<Return>", lambda _e: self._go_to_path())
        ttk.Button(path_row, text="이동", command=self._go_to_path).pack(side="left", padx=2)
        self.up_btn = ttk.Button(path_row, text="⬆ 상위", command=self._go_parent)
        self.up_btn.pack(side="left", padx=2)

        # 필터
        filter_row = ttk.Frame(body)
        filter_row.pack(fill="x", padx=15, pady=2)
        ttk.Label(filter_row, text="필터:").pack(side="left")
        self.filter_var = tk.StringVar()
        filter_entry = ttk.Entry(filter_row, textvariable=self.filter_var, width=24)
        filter_entry.pack(side="left", padx=4)
        filter_entry.bind("<KeyRelease>", lambda _e: self._apply_filter_to_tree())
        self.epub_only_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            filter_row,
            text="EPUB만",
            variable=self.epub_only_var,
            command=self._apply_filter_to_tree,
        ).pack(side="left", padx=8)
        self.summary_label = ttk.Label(filter_row, text="", foreground=HINT_COLOR)
        self.summary_label.pack(side="right", padx=4)

        # 파일 트리
        tree_frame = ttk.LabelFrame(body, text=" 기기 파일 목록 ")
        tree_frame.pack(fill="both", expand=True, padx=15, pady=6)

        columns = ("kind", "name", "size")
        self.file_tree = create_scrolled_tree(
            tree_frame, columns, height=12, selectmode="extended"
        )
        self.file_tree.heading("kind", text="종류")
        self.file_tree.heading("name", text="이름")
        self.file_tree.heading("size", text="크기")
        self.file_tree.column("kind", width=70, minwidth=50, anchor="center")
        self.file_tree.column("name", width=420, minwidth=160, anchor="w")
        self.file_tree.column("size", width=100, minwidth=70, anchor="e")
        self.file_tree.bind("<Double-1>", self._on_double_click)

        # 액션 버튼 1행
        actions = ttk.Frame(body)
        actions.pack(fill="x", padx=15, pady=(2, 2))
        self.delete_btn = ttk.Button(actions, text="🗑 선택 삭제", command=self._delete_selected)
        self.delete_btn.pack(side="left", padx=3)
        self.mkdir_btn = ttk.Button(actions, text="📂 폴더 생성", command=self._mkdir)
        self.mkdir_btn.pack(side="left", padx=3)
        self.rename_btn = ttk.Button(actions, text="✏ 이름 변경", command=self._rename_selected)
        self.rename_btn.pack(side="left", padx=3)
        self.move_btn = ttk.Button(actions, text="➡ 이동", command=self._move_selected)
        self.move_btn.pack(side="left", padx=3)
        self.download_btn = ttk.Button(actions, text="⬇ PC로 다운로드", command=self._download_selected)
        self.download_btn.pack(side="left", padx=3)
        self.upload_btn = ttk.Button(actions, text="⬆ 현재 폴더로 업로드", command=self._upload_to_current)
        self.upload_btn.pack(side="left", padx=3)

        # 액션 2행: 오래된 EPUB 정리
        cleanup = ttk.Frame(body)
        cleanup.pack(fill="x", padx=15, pady=(2, 10))
        ttk.Label(cleanup, text="오래된 동기화 EPUB:").pack(side="left")
        self.cleanup_days_var = tk.StringVar(value="14")
        self.cleanup_days_sp = ttk.Spinbox(
            cleanup, from_=1, to=365, width=5, textvariable=self.cleanup_days_var
        )
        self.cleanup_days_sp.pack(side="left", padx=4)
        ttk.Label(cleanup, text="일 이상").pack(side="left")
        self.select_old_btn = ttk.Button(
            cleanup, text="후보 선택", command=self._select_old_sync_epubs
        )
        self.select_old_btn.pack(side="left", padx=6)
        self.cleanup_old_btn = ttk.Button(
            cleanup, text="🧹 오래된 EPUB 삭제…", command=self._cleanup_old_sync_epubs
        )
        self.cleanup_old_btn.pack(side="left", padx=3)

        self._action_buttons = (
            self.refresh_btn,
            self.up_btn,
            self.delete_btn,
            self.mkdir_btn,
            self.rename_btn,
            self.move_btn,
            self.download_btn,
            self.upload_btn,
            self.select_old_btn,
            self.cleanup_old_btn,
        )

    # ------------------------------------------------------------------
    # 설정
    # ------------------------------------------------------------------

