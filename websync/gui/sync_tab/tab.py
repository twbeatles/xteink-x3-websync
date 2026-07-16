"""뉴스 동기화 탭 (조립)."""
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

from websync.gui.sync_tab.connection import SyncConnectionMixin
from websync.gui.sync_tab.schedule import SyncScheduleMixin
from websync.gui.sync_tab.devices import SyncDevicesMixin
from websync.gui.sync_tab.sites import SyncSitesMixin
from websync.gui.sync_tab.preview import SyncPreviewMixin


class SyncTab(
    SyncConnectionMixin,
    SyncScheduleMixin,
    SyncDevicesMixin,
    SyncSitesMixin,
    SyncPreviewMixin,
    ttk.Frame,
):
    """뉴스 동기화 및 일반 설정을 담당하는 탭"""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.service = app.service
        self.config_manager = app.service.config_manager
        self.scheduler = app.scheduler

        self._preview_data = []  # 프리뷰 기사 데이터 임시 저장
        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        # 1. 기기 및 경로 설정
        settings_frame = ttk.LabelFrame(body, text=" 기기 및 경로 설정 ")
        settings_frame.pack(fill="x", padx=15, pady=8)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="X3 주소 (IP/호스트):").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.ip_entry = ttk.Entry(settings_frame, width=22, font=("Consolas", 10))
        self.ip_entry.grid(row=0, column=1, padx=5, pady=6, sticky="we")
        self.test_conn_btn = ttk.Button(settings_frame, text="연결 확인", command=self._test_connection)
        self.test_conn_btn.grid(row=0, column=2, padx=5, pady=6)
        self.conn_status_label = ttk.Label(settings_frame, text="미확인", foreground=YELLOW_COLOR)
        self.conn_status_label.grid(row=0, column=3, padx=10, pady=6, sticky="w")

        ttk.Label(settings_frame, text="출력 저장 폴더:").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.dir_entry = ttk.Entry(settings_frame)
        self.dir_entry.grid(row=1, column=1, padx=5, pady=6, sticky="we")
        ttk.Button(settings_frame, text="폴더 선택", command=self._browse_directory).grid(row=1, column=2, padx=5, pady=6)
        ttk.Button(settings_frame, text="📂 열기", command=self._open_output_folder).grid(row=1, column=3, padx=5, pady=6)

        self.app._bind_autosave(self.ip_entry)
        self.app._bind_autosave(self.dir_entry)

        # 2. 추가 기기 관리
        devices_frame = ttk.LabelFrame(body, text=" 추가 X3 기기 (다중 무선 전송) ")
        devices_frame.pack(fill="x", padx=15, pady=5)
        devices_frame.columnconfigure(0, weight=1)

        devices_inner = ttk.Frame(devices_frame)
        devices_inner.pack(fill="x", padx=10, pady=8)
        devices_inner.columnconfigure(0, weight=1)
        devices_inner.rowconfigure(0, weight=1)

        tree_holder = ttk.Frame(devices_inner)
        tree_holder.grid(row=0, column=0, sticky="nsew")
        self.devices_tree = create_scrolled_tree(
            tree_holder, ("name", "ip"), height=3, padx=0, pady=0
        )
        self.devices_tree.heading("name", text="기기 이름")
        self.devices_tree.heading("ip", text="IP/호스트")
        self.devices_tree.column("name", width=180, minwidth=100)
        self.devices_tree.column("ip", width=220, minwidth=120)

        dev_btn = ttk.Frame(devices_inner)
        dev_btn.grid(row=0, column=1, padx=(8, 0), sticky="n")
        ttk.Button(dev_btn, text="기기 추가", command=self._add_device_popup).pack(fill="x", pady=2)
        ttk.Button(dev_btn, text="선택 삭제", command=self._remove_device).pack(fill="x", pady=2)

        ttk.Label(
            devices_frame,
            text="기본 X3 주소 외 추가 기기를 등록하면 동기화 시 모든 기기로 전송합니다.",
            font=("Malgun Gothic", 8),
            foreground=HINT_COLOR,
        ).pack(fill="x", padx=10, pady=(0, 6))

        # 3. 폰트 및 스타일 최적화
        font_frame = ttk.LabelFrame(body, text=" 한국어 가독성 스타일 최적화 (EPUB 포맷팅) ")
        font_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(font_frame, text="폰트:").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.font_cb = ttk.Combobox(
            font_frame,
            values=["serif", "sans-serif", "KoPubWorldBatang", "NanumGothic", "Malgun Gothic"],
            width=15,
            state="readonly",
        )
        self.font_cb.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        self.font_cb.set("serif")
        self.font_cb.bind("<<ComboboxSelected>>", lambda _e: self.app._save_ui_settings())

        ttk.Label(font_frame, text="글자 크기:").grid(row=0, column=2, padx=15, pady=6, sticky="w")
        self.font_size_sp = ttk.Spinbox(font_frame, from_=10, to=30, width=5)
        self.font_size_sp.grid(row=0, column=3, padx=5, pady=6, sticky="w")
        self.font_size_sp.set("16")
        self.app._bind_autosave(self.font_size_sp)

        ttk.Label(font_frame, text="줄 간격:").grid(row=0, column=4, padx=15, pady=6, sticky="w")
        self.line_height_sp = ttk.Spinbox(font_frame, from_=1.0, to=3.0, increment=0.1, width=5)
        self.line_height_sp.grid(row=0, column=5, padx=5, pady=6, sticky="w")
        self.line_height_sp.set("1.7")
        self.app._bind_autosave(self.line_height_sp)

        self.cover_var = tk.BooleanVar(value=True)
        cover_cb = ttk.Checkbutton(font_frame, text="EPUB 표지 자동 생성", variable=self.cover_var, command=self.app._save_ui_settings)
        cover_cb.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="w")

        # 4. 사이트 관리
        sites_frame = ttk.LabelFrame(body, text=" 동기화 대상 사이트 관리 ")
        sites_frame.pack(fill="x", padx=15, pady=5)

        columns = ("name", "type", "enabled", "url")
        self.tree = create_scrolled_tree(sites_frame, columns, height=6)
        self.tree.heading("name", text="사이트 이름")
        self.tree.heading("type", text="유형")
        self.tree.heading("enabled", text="활성화")
        self.tree.heading("url", text="URL")
        self.tree.column("name", width=140, minwidth=80, anchor="w")
        self.tree.column("type", width=80, minwidth=60, anchor="center")
        self.tree.column("enabled", width=55, minwidth=45, anchor="center")
        self.tree.column("url", width=370, minwidth=120, anchor="w")
        self.tree.bind("<Double-1>", lambda _e: self._edit_site_popup())

        btn_frame = ttk.Frame(sites_frame)
        btn_frame.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(btn_frame, text="사이트 추가", command=self._add_site_popup).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="사이트 수정", command=self._edit_site_popup).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="선택 삭제", command=self._delete_site).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="활성 토글", command=self._toggle_site_enabled).pack(side="left", padx=3)
        
        # M5: Import / Export 버튼
        ttk.Button(btn_frame, text="설정 가져오기", command=self._import_sites_action).pack(side="right", padx=3)
        ttk.Button(btn_frame, text="설정 내보내기", command=self._export_sites_action).pack(side="right", padx=3)

        # 5. 하단 그리드: 직접 전송 + 스케줄러
        bottom_grid = ttk.Frame(body)
        bottom_grid.pack(fill="x", padx=15, pady=5)
        bottom_grid.columnconfigure(0, weight=1)
        bottom_grid.columnconfigure(1, weight=1)

        upload_frame = ttk.LabelFrame(bottom_grid, text=" 로컬 파일 X3 직접 전송 ")
        upload_frame.grid(row=0, column=0, padx=(0, 5), sticky="nswe")
        upload_frame.columnconfigure(0, weight=1)
        self.file_entry = ttk.Entry(upload_frame)
        self.file_entry.grid(row=0, column=0, padx=8, pady=10, sticky="we")
        ttk.Button(upload_frame, text="...", width=3, command=self._browse_file).grid(row=0, column=1, padx=3, pady=10)
        self.direct_upload_btn = ttk.Button(upload_frame, text="기기로 직접 전송", command=self._direct_upload)
        self.direct_upload_btn.grid(row=0, column=2, padx=8, pady=10)

        scheduler_frame = ttk.LabelFrame(bottom_grid, text=" 자동 스케줄 설정 ")
        scheduler_frame.grid(row=0, column=1, padx=(5, 0), sticky="nswe")
        ttk.Label(scheduler_frame, text="매일 시간:").grid(row=0, column=0, padx=8, pady=10, sticky="w")
        self.hour_cb = ttk.Combobox(scheduler_frame, values=[f"{i:02d}" for i in range(24)], width=3, state="readonly")
        self.hour_cb.grid(row=0, column=1, padx=2, pady=10)
        self.min_cb = ttk.Combobox(scheduler_frame, values=[f"{i:02d}" for i in range(60)], width=3, state="readonly")
        self.min_cb.grid(row=0, column=2, padx=2, pady=10)
        ttk.Button(scheduler_frame, text="등록", command=self._register_schedule).grid(row=0, column=3, padx=3, pady=10)
        ttk.Button(scheduler_frame, text="해제", command=self._unregister_schedule).grid(row=0, column=4, padx=3, pady=10)
        self.sched_status_label = ttk.Label(scheduler_frame, text="스케줄 확인 중...", font=("Malgun Gothic", 8), foreground=HINT_COLOR)
        self.sched_status_label.grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 6), sticky="w")

    # ------------------------------------------------------------------
    # 연결 및 파일 브라우징
    # ------------------------------------------------------------------

