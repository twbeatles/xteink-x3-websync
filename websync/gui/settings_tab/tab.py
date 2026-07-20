"""고급·서버 설정 탭 (조립)."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.gui.widgets import (
    RED_COLOR, GREEN_COLOR, ACCENT_COLOR, HINT_COLOR, BG_COLOR,
    create_scrollable_frame, setup_dialog
)
from websync.core.paths import resolve_path
from websync.core.logger import get_log_dir
from websync.servers.opds import OPDSServer
from websync.servers.web_dashboard import WebDashboard
from websync.watch.calibre import CalibreWatcher

from websync.gui.settings_tab.epub_settings import SettingsEpubMixin
from websync.gui.settings_tab.servers import SettingsServersMixin
from websync.gui.settings_tab.watch import SettingsWatchMixin
from websync.gui.settings_tab.ai_translation import SettingsAiTranslationMixin
from websync.gui.settings_tab.backup_sync import SettingsBackupSyncMixin


class SettingsTab(
    SettingsEpubMixin,
    SettingsServersMixin,
    SettingsWatchMixin,
    SettingsAiTranslationMixin,
    SettingsBackupSyncMixin,
    ttk.Frame,
):
    """서버 제어 및 AI, 번역, 합본, 테마 등 고급 설정을 담당하는 탭"""
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self.service = app.service
        self.config_manager = app.service.config_manager

        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        # 0. M4 & M7: EPUB 병합 모드 및 테마 설정
        epub_style_frame = ttk.LabelFrame(body, text=" EPUB 빌드 테마 & 병합 방식 설정 ")
        epub_style_frame.pack(fill="x", padx=15, pady=10)
        epub_style_frame.columnconfigure(1, weight=1)

        # M4: 합본 모드 라디오 버튼
        ttk.Label(epub_style_frame, text="병합 방식:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.merge_mode_var = tk.StringVar(value="per_site")
        self.per_site_rb = ttk.Radiobutton(
            epub_style_frame, text="사이트별 개별 EPUB 전송", variable=self.merge_mode_var, value="per_site", command=self._save_epub_settings
        )
        self.per_site_rb.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.digest_rb = ttk.Radiobutton(
            epub_style_frame, text="하나의 일간 합본 EPUB으로 전송", variable=self.merge_mode_var, value="daily_digest", command=self._save_epub_settings
        )
        self.digest_rb.grid(row=0, column=2, padx=5, pady=8, sticky="w")

        # M7: 테마 프리셋 드롭다운
        ttk.Label(epub_style_frame, text="EPUB 테마:").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.epub_theme_cb = ttk.Combobox(
            epub_style_frame, values=["default", "serif_classic", "sans_modern", "dark_eink", "custom"], state="readonly", width=15
        )
        self.epub_theme_cb.grid(row=1, column=1, padx=5, pady=8, sticky="w")
        self.epub_theme_cb.set("default")
        self.epub_theme_cb.bind("<<ComboboxSelected>>", self._on_theme_changed)

        # M7: 커스텀 CSS 파일 경로
        ttk.Label(epub_style_frame, text="커스텀 CSS 경로:").grid(row=2, column=0, padx=10, pady=8, sticky="w")
        self.custom_css_entry = ttk.Entry(epub_style_frame)
        self.custom_css_entry.grid(row=2, column=1, columnspan=2, padx=5, pady=8, sticky="we")
        self.custom_css_btn = ttk.Button(epub_style_frame, text="찾아보기", command=self._browse_custom_css)
        self.custom_css_btn.grid(row=2, column=3, padx=10, pady=8)
        self.app._bind_autosave(self.custom_css_entry)

        # 1. OPDS 서버
        opds_frame = ttk.LabelFrame(body, text=" 📡 OPDS 카탈로그 서버 ")
        opds_frame.pack(fill="x", padx=15, pady=10)
        opds_frame.columnconfigure(4, weight=1)
        ttk.Label(opds_frame, text="포트:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.opds_port_sp = ttk.Spinbox(opds_frame, from_=1024, to=65535, width=6)
        self.opds_port_sp.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.opds_port_sp.set("8765")
        self.opds_start_btn = ttk.Button(opds_frame, text="▶ 서버 시작", command=self._toggle_opds)
        self.opds_start_btn.grid(row=0, column=2, padx=5, pady=8)
        self.opds_status_label = ttk.Label(opds_frame, text="중지됨", foreground=RED_COLOR)
        self.opds_status_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.opds_url_label = ttk.Label(opds_frame, text="", foreground=ACCENT_COLOR, cursor="hand2")
        self.opds_url_label.grid(row=1, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.opds_url_label.bind("<Button-1>", lambda e: self.app._open_url(self.opds_url_label.cget("text")))
        self.opds_allow_lan_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opds_frame, text="LAN 공개 (0.0.0.0)", variable=self.opds_allow_lan_var, command=self.app._save_ui_settings).grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="w")
        ttk.Label(opds_frame, text="기본은 localhost만 허용. LAN 공개 시 API 키 인증 필요.", font=("Malgun Gothic", 8), foreground=HINT_COLOR).grid(row=3, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.opds_api_key_label = ttk.Label(opds_frame, text="", font=("Consolas", 8), foreground=HINT_COLOR)
        self.opds_api_key_label.grid(row=4, column=0, columnspan=5, padx=10, pady=(0, 8), sticky="w")
        self.app._bind_autosave(self.opds_port_sp)

        # 2. 웹 대시보드
        web_frame = ttk.LabelFrame(body, text=" 🌐 웹 대시보드 ")
        web_frame.pack(fill="x", padx=15, pady=5)
        web_frame.columnconfigure(4, weight=1)
        ttk.Label(web_frame, text="포트:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.web_port_sp = ttk.Spinbox(web_frame, from_=1024, to=65535, width=6)
        self.web_port_sp.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.web_port_sp.set("8766")
        self.web_start_btn = ttk.Button(web_frame, text="▶ 서버 시작", command=self._toggle_web)
        self.web_start_btn.grid(row=0, column=2, padx=5, pady=8)
        self.web_status_label = ttk.Label(web_frame, text="중지됨", foreground=RED_COLOR)
        self.web_status_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.web_url_label = ttk.Label(web_frame, text="", foreground=ACCENT_COLOR, cursor="hand2")
        self.web_url_label.grid(row=1, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.web_url_label.bind("<Button-1>", lambda e: self.app._open_url(self.web_url_label.cget("text")))
        self.web_allow_lan_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(web_frame, text="LAN 공개 (0.0.0.0)", variable=self.web_allow_lan_var, command=self.app._save_ui_settings).grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="w")
        ttk.Label(
            web_frame,
            text="⚠️ LAN 공개 시 HTTP 평문 전송 — 신뢰할 수 있는 네트워크에서만 사용하세요.",
            font=("Malgun Gothic", 8),
            foreground=RED_COLOR,
        ).grid(row=3, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.web_token_label = ttk.Label(web_frame, text="", font=("Consolas", 8), foreground=HINT_COLOR)
        self.web_token_label.grid(row=4, column=0, columnspan=5, padx=10, pady=(0, 8), sticky="w")
        self.app._bind_autosave(self.web_port_sp)

        # 3. Calibre Watch
        watch_frame = ttk.LabelFrame(body, text=" 👁 Calibre 서재 자동 감시 (새 파일 추가 시 자동 전송) ")
        watch_frame.pack(fill="x", padx=15, pady=5)
        watch_frame.columnconfigure(1, weight=1)
        ttk.Label(watch_frame, text="감시 폴더:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.watch_dir_entry = ttk.Entry(watch_frame)
        self.watch_dir_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(watch_frame, text="폴더 선택", command=self._browse_watch_dir).grid(row=0, column=2, padx=5, pady=8)
        self.watch_start_btn = ttk.Button(watch_frame, text="▶ 감시 시작", command=self._toggle_watch)
        self.watch_start_btn.grid(row=0, column=3, padx=5, pady=8)
        self.watch_status_label = ttk.Label(watch_frame, text="감시 중지됨", foreground=RED_COLOR)
        self.watch_status_label.grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="w")
        self.app._bind_autosave(self.watch_dir_entry)

        # 4. AI 요약 설정
        ai_frame = ttk.LabelFrame(body, text=" 🤖 AI 기사 요약 설정 (선택) ")
        ai_frame.pack(fill="x", padx=15, pady=5)

        self.ai_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(ai_frame, text="AI 요약 활성화", variable=self.ai_enabled_var).grid(row=0, column=0, padx=10, pady=6, sticky="w")

        ttk.Label(ai_frame, text="프로바이더:").grid(row=0, column=1, padx=10, pady=6, sticky="w")
        self.ai_provider_cb = ttk.Combobox(ai_frame, values=["openai", "ollama"], width=10, state="readonly")
        self.ai_provider_cb.grid(row=0, column=2, padx=5, pady=6)
        self.ai_provider_cb.set("openai")

        ttk.Label(ai_frame, text="API Key / Ollama Host:").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.ai_key_entry = ttk.Entry(ai_frame, width=40, show="*")
        self.ai_key_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=6, sticky="w")

        ttk.Button(ai_frame, text="저장", command=self._save_ai_settings).grid(row=1, column=3, padx=10, pady=6)

        # 5. 번역 설정
        trans_frame = ttk.LabelFrame(body, text=" 🌐 번역 설정 (선택) ")
        trans_frame.pack(fill="x", padx=15, pady=5)

        self.trans_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(trans_frame, text="번역 활성화", variable=self.trans_enabled_var).grid(row=0, column=0, padx=10, pady=6, sticky="w")

        ttk.Label(trans_frame, text="프로바이더:").grid(row=0, column=1, padx=10, pady=6, sticky="w")
        self.trans_provider_cb = ttk.Combobox(trans_frame, values=["googletrans", "libretranslate"], width=14, state="readonly")
        self.trans_provider_cb.grid(row=0, column=2, padx=5, pady=6)
        self.trans_provider_cb.set("googletrans")

        ttk.Button(trans_frame, text="저장", command=self._save_trans_settings).grid(row=0, column=3, padx=10, pady=6)
        ttk.Label(trans_frame, text="※ googletrans: 사이트별 '번역'만 설정해도 동작. libretranslate: 전역 활성화 필요.", font=("Malgun Gothic", 8), foreground=HINT_COLOR).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="w")

        # 6. 클라우드 백업 동기화 (OneDrive 등)
        self._build_backup_sync_section(body)

        # 7. 로그 폴더 열기
        log_frame = ttk.LabelFrame(body, text=" 📂 로그 파일 ")
        log_frame.pack(fill="x", padx=15, pady=5)
        ttk.Button(log_frame, text="📂 로그 폴더 열기", command=self._open_log_folder).pack(side="left", padx=10, pady=8)
        ttk.Label(log_frame, text="logs/ 폴더에 날짜별 sync_YYYY-MM-DD.log 파일이 저장됩니다.", font=("Malgun Gothic", 8), foreground=HINT_COLOR).pack(side="left", padx=5, pady=8)

    # ------------------------------------------------------------------
    # M7 & M4: EPUB 설정 및 CSS 로딩
    # ------------------------------------------------------------------

