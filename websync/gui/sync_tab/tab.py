"""뉴스 동기화 탭 (CustomTkinter 현대적 카드 UI 적용)."""
from __future__ import annotations

import os
import sys
import hashlib
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

from websync.gui.widgets import (
    CardFrame, COLOR_CARD_BG, COLOR_FG, COLOR_SECONDARY_FG, COLOR_ACCENT,
    COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING, get_font,
    create_scrollable_frame, create_scrolled_tree, setup_dialog
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
    ctk.CTkFrame,
):
    """뉴스 동기화 및 일반 설정을 담당하는 탭 패널"""
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.service = app.service
        self.config_manager = app.service.config_manager
        self.scheduler = app.scheduler

        self._preview_data = []  # 프리뷰 기사 데이터 임시 저장
        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        # 1. 기기 및 경로 설정 카드
        settings_card = CardFrame(body, title="📱 기기 및 경로 설정", subtitle="e-ink 기기 접속 정보 및 빌드 저장 폴더")
        settings_card.pack(fill="x", padx=8, pady=6)

        grid_frame = ctk.CTkFrame(settings_card, fg_color="transparent")
        grid_frame.pack(fill="x", padx=12, pady=10)
        grid_frame.columnconfigure(1, weight=1)

        ctk.CTkLabel(grid_frame, text="X3 주소 (IP/호스트):", font=get_font(13), anchor="w").grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.ip_entry = ctk.CTkEntry(grid_frame, placeholder_text="192.168.x.x 또는 호스트명", font=get_font(12), height=34)
        self.ip_entry.grid(row=0, column=1, padx=4, pady=6, sticky="we")

        self.test_conn_btn = ctk.CTkButton(grid_frame, text="연결 확인", font=get_font(12, "bold"), width=100, height=34, command=self._test_connection)
        self.test_conn_btn.grid(row=0, column=2, padx=6, pady=6)

        self.conn_status_label = ctk.CTkLabel(grid_frame, text="미확인", text_color=COLOR_WARNING[0], font=get_font(13, "bold"))
        self.conn_status_label.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        ctk.CTkLabel(grid_frame, text="출력 저장 폴더:", font=get_font(13), anchor="w").grid(row=1, column=0, padx=(0, 8), pady=6, sticky="w")
        self.dir_entry = ctk.CTkEntry(grid_frame, font=get_font(12), height=34)
        self.dir_entry.grid(row=1, column=1, padx=4, pady=6, sticky="we")

        ctk.CTkButton(grid_frame, text="폴더 선택", font=get_font(12), width=100, height=34, command=self._browse_directory).grid(row=1, column=2, padx=6, pady=6)
        ctk.CTkButton(grid_frame, text="📂 열기", font=get_font(12), width=80, height=34, fg_color=("#e9ecef", "#343a40"), text_color=COLOR_FG, command=self._open_output_folder).grid(row=1, column=3, padx=4, pady=6)

        self.app._bind_autosave(self.ip_entry)
        self.app._bind_autosave(self.dir_entry)

        # 2. 추가 기기 관리 카드
        devices_card = CardFrame(body, title="📡 추가 X3 기기", subtitle="등록된 모든 기기로 동시 무선 전송")
        devices_card.pack(fill="x", padx=8, pady=6)

        dev_inner = ctk.CTkFrame(devices_card, fg_color="transparent")
        dev_inner.pack(fill="x", padx=12, pady=10)
        dev_inner.columnconfigure(0, weight=1)

        tree_holder = ctk.CTkFrame(dev_inner, fg_color="transparent")
        tree_holder.grid(row=0, column=0, sticky="nsew")

        self.devices_tree = create_scrolled_tree(
            tree_holder, ("name", "ip"), height=3, padx=0, pady=0
        )
        self.devices_tree.heading("name", text="기기 이름")
        self.devices_tree.heading("ip", text="IP/호스트")
        self.devices_tree.column("name", width=180, minwidth=100)
        self.devices_tree.column("ip", width=220, minwidth=120)

        dev_btn = ctk.CTkFrame(dev_inner, fg_color="transparent")
        dev_btn.grid(row=0, column=1, padx=(10, 0), sticky="n")
        ctk.CTkButton(dev_btn, text="기기 추가", font=get_font(12), width=95, height=32, command=self._add_device_popup).pack(fill="x", pady=2)
        ctk.CTkButton(dev_btn, text="선택 삭제", font=get_font(12), width=95, height=32, fg_color=COLOR_DANGER[0], hover_color=COLOR_DANGER[1], command=self._remove_device).pack(fill="x", pady=2)

        # 3. 폰트 및 스타일 최적화 카드 (기본 폰트를 맑은 고딕으로 설정)
        font_card = CardFrame(body, title="🎨 가독성 및 EPUB 스타일 최적화")
        font_card.pack(fill="x", padx=8, pady=6)

        font_inner = ctk.CTkFrame(font_card, fg_color="transparent")
        font_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(font_inner, text="폰트:", font=get_font(13)).grid(row=0, column=0, padx=(0, 6), pady=6, sticky="w")
        self.font_cb = ctk.CTkOptionMenu(
            font_inner,
            values=["Malgun Gothic", "serif", "sans-serif", "KoPubWorldBatang", "NanumGothic"],
            font=get_font(12),
            width=160,
            command=lambda _v: self.app._save_ui_settings()
        )
        self.font_cb.grid(row=0, column=1, padx=4, pady=6, sticky="w")
        self.font_cb.set("Malgun Gothic")

        ctk.CTkLabel(font_inner, text="글자 크기:", font=get_font(13)).grid(row=0, column=2, padx=(16, 6), pady=6, sticky="w")
        self.font_size_sp = ctk.CTkEntry(font_inner, font=get_font(12), width=55, height=32)
        self.font_size_sp.grid(row=0, column=3, padx=4, pady=6, sticky="w")
        self.font_size_sp.insert(0, "16")
        self.app._bind_autosave(self.font_size_sp)

        ctk.CTkLabel(font_inner, text="줄 간격:", font=get_font(13)).grid(row=0, column=4, padx=(16, 6), pady=6, sticky="w")
        self.line_height_sp = ctk.CTkEntry(font_inner, font=get_font(12), width=55, height=32)
        self.line_height_sp.grid(row=0, column=5, padx=4, pady=6, sticky="w")
        self.line_height_sp.insert(0, "1.7")
        self.app._bind_autosave(self.line_height_sp)

        self.cover_var = tk.BooleanVar(value=True)
        cover_cb = ctk.CTkCheckBox(
            font_inner,
            text="EPUB 표지 자동 생성",
            font=get_font(12),
            variable=self.cover_var,
            command=self.app._save_ui_settings
        )
        cover_cb.grid(row=1, column=0, columnspan=3, padx=4, pady=(6, 0), sticky="w")

        # 4. 사이트 관리 카드
        sites_card = CardFrame(body, title="🌐 동기화 대상 사이트 관리", subtitle="뉴스, RSS, 블로그 스크래핑 소스 설정")
        sites_card.pack(fill="x", padx=8, pady=6)

        columns = ("name", "type", "enabled", "url")
        self.tree = create_scrolled_tree(sites_card, columns, height=7)
        self.tree.heading("name", text="사이트 이름")
        self.tree.heading("type", text="유형")
        self.tree.heading("enabled", text="활성화")
        self.tree.heading("url", text="URL")
        self.tree.column("name", width=140, minwidth=80, anchor="w")
        self.tree.column("type", width=80, minwidth=60, anchor="center")
        self.tree.column("enabled", width=55, minwidth=45, anchor="center")
        self.tree.column("url", width=370, minwidth=120, anchor="w")
        self.tree.bind("<Double-1>", lambda _e: self._edit_site_popup())

        btn_frame = ctk.CTkFrame(sites_card, fg_color="transparent")
        btn_frame.pack(fill="x", padx=12, pady=(0, 10))

        ctk.CTkButton(btn_frame, text="사이트 추가", font=get_font(12), width=100, height=32, command=self._add_site_popup).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="사이트 수정", font=get_font(12), width=100, height=32, fg_color=("#e9ecef", "#343a40"), text_color=COLOR_FG, command=self._edit_site_popup).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="선택 삭제", font=get_font(12), width=95, height=32, fg_color=COLOR_DANGER[0], hover_color=COLOR_DANGER[1], command=self._delete_site).pack(side="left", padx=3)
        ctk.CTkButton(btn_frame, text="활성 토글", font=get_font(12), width=95, height=32, fg_color=("#e9ecef", "#343a40"), text_color=COLOR_FG, command=self._toggle_site_enabled).pack(side="left", padx=3)

        ctk.CTkButton(btn_frame, text="설정 내보내기", font=get_font(12), width=110, height=32, fg_color=("#e9ecef", "#343a40"), text_color=COLOR_FG, command=self._export_sites_action).pack(side="right", padx=3)
        ctk.CTkButton(btn_frame, text="설정 가져오기", font=get_font(12), width=110, height=32, fg_color=("#e9ecef", "#343a40"), text_color=COLOR_FG, command=self._import_sites_action).pack(side="right", padx=3)

        # 5. 하단 직접 전송 & 스케줄 설정
        bottom_row = ctk.CTkFrame(body, fg_color="transparent")
        bottom_row.pack(fill="x", padx=8, pady=6)
        bottom_row.columnconfigure(0, weight=1)
        bottom_row.columnconfigure(1, weight=1)

        upload_card = CardFrame(bottom_row, title="📤 로컬 파일 직접 전송")
        upload_card.grid(row=0, column=0, padx=(0, 4), sticky="nsew")

        upload_inner = ctk.CTkFrame(upload_card, fg_color="transparent")
        upload_inner.pack(fill="x", padx=10, pady=10)
        upload_inner.columnconfigure(0, weight=1)

        self.file_entry = ctk.CTkEntry(upload_inner, placeholder_text="전송할 .epub 파일 선택", font=get_font(12), height=34)
        self.file_entry.grid(row=0, column=0, padx=4, pady=8, sticky="we")
        ctk.CTkButton(upload_inner, text="...", font=get_font(12), width=40, height=34, command=self._browse_file).grid(row=0, column=1, padx=4, pady=8)
        self.direct_upload_btn = ctk.CTkButton(upload_inner, text="전송", font=get_font(12, "bold"), width=70, height=34, command=self._direct_upload)
        self.direct_upload_btn.grid(row=0, column=2, padx=4, pady=8)

        scheduler_card = CardFrame(bottom_row, title="⏰ 매일 자동 스케줄 설정")
        scheduler_card.grid(row=0, column=1, padx=(4, 0), sticky="nsew")

        sched_inner = ctk.CTkFrame(scheduler_card, fg_color="transparent")
        sched_inner.pack(fill="x", padx=10, pady=8)

        ctk.CTkLabel(sched_inner, text="매일:", font=get_font(13)).grid(row=0, column=0, padx=(0, 4), pady=4, sticky="w")
        self.hour_cb = ctk.CTkOptionMenu(sched_inner, values=[f"{i:02d}" for i in range(24)], font=get_font(12), width=65, height=32)
        self.hour_cb.grid(row=0, column=1, padx=2, pady=4)
        self.min_cb = ctk.CTkOptionMenu(sched_inner, values=[f"{i:02d}" for i in range(60)], font=get_font(12), width=65, height=32)
        self.min_cb.grid(row=0, column=2, padx=2, pady=4)

        ctk.CTkButton(sched_inner, text="등록", font=get_font(12, "bold"), width=65, height=32, command=self._register_schedule).grid(row=0, column=3, padx=4, pady=4)
        ctk.CTkButton(sched_inner, text="해제", font=get_font(12), width=65, height=32, fg_color=COLOR_DANGER[0], hover_color=COLOR_DANGER[1], command=self._unregister_schedule).grid(row=0, column=4, padx=2, pady=4)

        self.sched_status_label = ctk.CTkLabel(scheduler_card, text="스케줄 확인 중...", font=get_font(12), text_color=COLOR_SECONDARY_FG)
        self.sched_status_label.pack(fill="x", padx=10, pady=(0, 8), anchor="w")
