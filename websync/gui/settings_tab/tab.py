"""고급·서버 설정 탭 (CustomTkinter 카드 레이아웃 적용)."""
from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import customtkinter as ctk

from websync.gui.widgets import (
    CardFrame, COLOR_CARD_BG, COLOR_FG, COLOR_SECONDARY_FG, COLOR_ACCENT,
    COLOR_SUCCESS, COLOR_DANGER, COLOR_WARNING, get_font,
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
    ctk.CTkFrame,
):
    """서버 제어 및 AI, 번역, 합본, 테마 등 고급 설정을 담당하는 탭 패널"""
    def __init__(self, parent, app):
        super().__init__(parent, fg_color="transparent")
        self.app = app
        self.service = app.service
        self.config_manager = app.service.config_manager

        self._build_ui()

    def _build_ui(self):
        body = create_scrollable_frame(self)

        # 0. 앱 테마 및 UI Appearance 설정 카드
        theme_card = CardFrame(body, title="🎨 애플리케이션 테마 및 UI 모드", subtitle="다크/라이트 모드 설정")
        theme_card.pack(fill="x", padx=8, pady=6)

        theme_inner = ctk.CTkFrame(theme_card, fg_color="transparent")
        theme_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkLabel(theme_inner, text="화면 테마:", font=get_font(13)).grid(row=0, column=0, padx=(0, 8), pady=4, sticky="w")
        self.app_theme_menu = ctk.CTkOptionMenu(
            theme_inner,
            values=["System", "Dark", "Light"],
            font=get_font(12),
            width=130,
            command=self._on_app_theme_changed
        )
        self.app_theme_menu.grid(row=0, column=1, padx=4, pady=4, sticky="w")
        curr_mode = self.service.config.get("appearance_mode", "System")
        self.app_theme_menu.set(curr_mode)

        # 1. EPUB 병합 모드 및 빌드 테마 카드
        epub_style_card = CardFrame(body, title="📚 EPUB 빌드 테마 & 병합 방식", subtitle="전자책 템플릿 및 css 스타일")
        epub_style_card.pack(fill="x", padx=8, pady=6)

        epub_inner = ctk.CTkFrame(epub_style_card, fg_color="transparent")
        epub_inner.pack(fill="x", padx=12, pady=10)
        epub_inner.columnconfigure(1, weight=1)

        ctk.CTkLabel(epub_inner, text="병합 방식:", font=get_font(13)).grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.merge_mode_var = tk.StringVar(value="per_site")
        self.per_site_rb = ctk.CTkRadioButton(
            epub_inner, text="사이트별 개별 EPUB", font=get_font(12), variable=self.merge_mode_var, value="per_site", command=self._save_epub_settings
        )
        self.per_site_rb.grid(row=0, column=1, padx=4, pady=6, sticky="w")
        self.digest_rb = ctk.CTkRadioButton(
            epub_inner, text="하나의 일간 합본 EPUB", font=get_font(12), variable=self.merge_mode_var, value="daily_digest", command=self._save_epub_settings
        )
        self.digest_rb.grid(row=0, column=2, padx=4, pady=6, sticky="w")

        ctk.CTkLabel(epub_inner, text="EPUB 테마:", font=get_font(13)).grid(row=1, column=0, padx=(0, 8), pady=6, sticky="w")
        self.epub_theme_cb = ctk.CTkOptionMenu(
            epub_inner, values=["default", "serif_classic", "sans_modern", "dark_eink", "custom"], font=get_font(12), width=160, command=self._on_theme_changed
        )
        self.epub_theme_cb.grid(row=1, column=1, padx=4, pady=6, sticky="w")
        self.epub_theme_cb.set("default")

        ctk.CTkLabel(epub_inner, text="커스텀 CSS:", font=get_font(13)).grid(row=2, column=0, padx=(0, 8), pady=6, sticky="w")
        self.custom_css_entry = ctk.CTkEntry(epub_inner, font=get_font(12), height=34)
        self.custom_css_entry.grid(row=2, column=1, padx=4, pady=6, sticky="we")
        self.custom_css_btn = ctk.CTkButton(epub_inner, text="찾아보기", font=get_font(12), width=90, height=34, command=self._browse_custom_css)
        self.custom_css_btn.grid(row=2, column=2, padx=4, pady=6)
        self.app._bind_autosave(self.custom_css_entry)

        # 2. OPDS 서버 카드
        opds_card = CardFrame(body, title="📡 OPDS 카탈로그 서버", subtitle="무선 전자책 다운로드 피드")
        opds_card.pack(fill="x", padx=8, pady=6)

        opds_inner = ctk.CTkFrame(opds_card, fg_color="transparent")
        opds_inner.pack(fill="x", padx=12, pady=10)
        opds_inner.columnconfigure(4, weight=1)

        ctk.CTkLabel(opds_inner, text="포트:", font=get_font(13)).grid(row=0, column=0, padx=(0, 6), pady=6, sticky="w")
        self.opds_port_sp = ctk.CTkEntry(opds_inner, font=get_font(12), width=75, height=32)
        self.opds_port_sp.grid(row=0, column=1, padx=4, pady=6, sticky="w")
        self.opds_port_sp.insert(0, "8765")

        self.opds_start_btn = ctk.CTkButton(opds_inner, text="▶ 서버 시작", font=get_font(12, "bold"), width=105, height=32, command=self._toggle_opds)
        self.opds_start_btn.grid(row=0, column=2, padx=6, pady=6)

        self.opds_status_label = ctk.CTkLabel(opds_inner, text="중지됨", text_color=COLOR_DANGER[0], font=get_font(13, "bold"))
        self.opds_status_label.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        self.opds_url_label = ctk.CTkLabel(opds_inner, text="", font=get_font(12), text_color=COLOR_ACCENT[0], cursor="hand2")
        self.opds_url_label.grid(row=1, column=0, columnspan=5, padx=4, pady=(0, 4), sticky="w")
        self.opds_url_label.bind("<Button-1>", lambda e: self.app._open_url(self.opds_url_label.cget("text")))

        self.opds_allow_lan_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(opds_inner, text="LAN 공개 (0.0.0.0)", font=get_font(12), variable=self.opds_allow_lan_var, command=self.app._save_ui_settings).grid(row=2, column=0, columnspan=2, padx=4, pady=(0, 4), sticky="w")

        self.opds_api_key_label = ctk.CTkLabel(opds_inner, text="", font=get_font(12), text_color=COLOR_SECONDARY_FG)
        self.opds_api_key_label.grid(row=3, column=0, columnspan=4, padx=4, pady=(0, 6), sticky="w")

        self.opds_key_show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(opds_inner, text="API 키 표시", font=get_font(12), variable=self.opds_key_show_var, command=self._refresh_opds_key_display).grid(row=3, column=4, padx=4, pady=(0, 6), sticky="e")
        self.app._bind_autosave(self.opds_port_sp)

        # 3. 웹 대시보드 카드
        web_card = CardFrame(body, title="🌐 웹 대시보드", subtitle="브라우저 모니터링 인터페이스")
        web_card.pack(fill="x", padx=8, pady=6)

        web_inner = ctk.CTkFrame(web_card, fg_color="transparent")
        web_inner.pack(fill="x", padx=12, pady=10)
        web_inner.columnconfigure(4, weight=1)

        ctk.CTkLabel(web_inner, text="포트:", font=get_font(13)).grid(row=0, column=0, padx=(0, 6), pady=6, sticky="w")
        self.web_port_sp = ctk.CTkEntry(web_inner, font=get_font(12), width=75, height=32)
        self.web_port_sp.grid(row=0, column=1, padx=4, pady=6, sticky="w")
        self.web_port_sp.insert(0, "8766")

        self.web_start_btn = ctk.CTkButton(web_inner, text="▶ 서버 시작", font=get_font(12, "bold"), width=105, height=32, command=self._toggle_web)
        self.web_start_btn.grid(row=0, column=2, padx=6, pady=6)

        self.web_status_label = ctk.CTkLabel(web_inner, text="중지됨", text_color=COLOR_DANGER[0], font=get_font(13, "bold"))
        self.web_status_label.grid(row=0, column=3, padx=8, pady=6, sticky="w")

        self.web_url_label = ctk.CTkLabel(web_inner, text="", font=get_font(12), text_color=COLOR_ACCENT[0], cursor="hand2")
        self.web_url_label.grid(row=1, column=0, columnspan=5, padx=4, pady=(0, 4), sticky="w")
        self.web_url_label.bind("<Button-1>", lambda e: self.app._open_url(self.web_url_label.cget("text")))

        self.web_allow_lan_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(web_inner, text="LAN 공개 (0.0.0.0)", font=get_font(12), variable=self.web_allow_lan_var, command=self.app._save_ui_settings).grid(row=2, column=0, columnspan=2, padx=4, pady=(0, 4), sticky="w")

        self.web_token_label = ctk.CTkLabel(web_inner, text="", font=get_font(12), text_color=COLOR_SECONDARY_FG)
        self.web_token_label.grid(row=3, column=0, columnspan=4, padx=4, pady=(0, 6), sticky="w")

        self.web_token_show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(web_inner, text="토큰 표시", font=get_font(12), variable=self.web_token_show_var, command=self._refresh_web_token_display).grid(row=3, column=4, padx=4, pady=(0, 6), sticky="e")
        self.app._bind_autosave(self.web_port_sp)

        # 4. Calibre Watch 카드
        watch_card = CardFrame(body, title="👁 Calibre 서재 자동 감시", subtitle="폴더 내 새 도서 추가 시 자동 전송")
        watch_card.pack(fill="x", padx=8, pady=6)

        watch_inner = ctk.CTkFrame(watch_card, fg_color="transparent")
        watch_inner.pack(fill="x", padx=12, pady=10)
        watch_inner.columnconfigure(1, weight=1)

        ctk.CTkLabel(watch_inner, text="감시 폴더:", font=get_font(13)).grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")
        self.watch_dir_entry = ctk.CTkEntry(watch_inner, font=get_font(12), height=34)
        self.watch_dir_entry.grid(row=0, column=1, padx=4, pady=6, sticky="we")

        ctk.CTkButton(watch_inner, text="폴더 선택", font=get_font(12), width=90, height=34, command=self._browse_watch_dir).grid(row=0, column=2, padx=4, pady=6)
        self.watch_start_btn = ctk.CTkButton(watch_inner, text="▶ 감시 시작", font=get_font(12, "bold"), width=105, height=34, command=self._toggle_watch)
        self.watch_start_btn.grid(row=0, column=3, padx=4, pady=6)

        self.watch_status_label = ctk.CTkLabel(watch_inner, text="감시 중지됨", text_color=COLOR_DANGER[0], font=get_font(12))
        self.watch_status_label.grid(row=1, column=0, columnspan=4, padx=4, pady=(0, 4), sticky="w")
        self.app._bind_autosave(self.watch_dir_entry)

        # 5. AI 요약 카드
        ai_card = CardFrame(body, title="🤖 AI 기사 요약 설정", subtitle="OpenAI 및 Ollama 연동")
        ai_card.pack(fill="x", padx=8, pady=6)

        ai_inner = ctk.CTkFrame(ai_card, fg_color="transparent")
        ai_inner.pack(fill="x", padx=12, pady=10)

        self.ai_enabled_var = tk.BooleanVar()
        ctk.CTkCheckBox(ai_inner, text="AI 요약 활성화", font=get_font(12), variable=self.ai_enabled_var).grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")

        ctk.CTkLabel(ai_inner, text="프로바이더:", font=get_font(13)).grid(row=0, column=1, padx=(8, 4), pady=6, sticky="w")
        self.ai_provider_cb = ctk.CTkOptionMenu(ai_inner, values=["openai", "ollama"], font=get_font(12), width=120)
        self.ai_provider_cb.grid(row=0, column=2, padx=4, pady=6, sticky="w")
        self.ai_provider_cb.set("openai")

        ctk.CTkLabel(ai_inner, text="API Key / Host:", font=get_font(13)).grid(row=1, column=0, padx=(0, 8), pady=6, sticky="w")
        self.ai_key_entry = ctk.CTkEntry(ai_inner, font=get_font(12), width=280, height=34, show="*")
        self.ai_key_entry.grid(row=1, column=1, columnspan=2, padx=4, pady=6, sticky="w")

        self.ai_key_show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(ai_inner, text="표시", font=get_font(12), variable=self.ai_key_show_var, command=self._toggle_ai_key_visibility).grid(row=1, column=3, padx=6, pady=6)
        ctk.CTkButton(ai_inner, text="저장", font=get_font(12, "bold"), width=75, height=34, command=self._save_ai_settings).grid(row=1, column=4, padx=6, pady=6)

        # 6. 번역 카드
        trans_card = CardFrame(body, title="🌐 번역 설정", subtitle="자동 언어 번역 엔진")
        trans_card.pack(fill="x", padx=8, pady=6)

        trans_inner = ctk.CTkFrame(trans_card, fg_color="transparent")
        trans_inner.pack(fill="x", padx=12, pady=10)

        self.trans_enabled_var = tk.BooleanVar()
        ctk.CTkCheckBox(trans_inner, text="번역 활성화", font=get_font(12), variable=self.trans_enabled_var).grid(row=0, column=0, padx=(0, 8), pady=6, sticky="w")

        ctk.CTkLabel(trans_inner, text="프로바이더:", font=get_font(13)).grid(row=0, column=1, padx=(8, 4), pady=6, sticky="w")
        self.trans_provider_cb = ctk.CTkOptionMenu(trans_inner, values=["googletrans", "libretranslate"], font=get_font(12), width=140, command=lambda _v: self._update_trans_key_state())
        self.trans_provider_cb.grid(row=0, column=2, padx=4, pady=6, sticky="w")
        self.trans_provider_cb.set("googletrans")

        ctk.CTkButton(trans_inner, text="저장", font=get_font(12, "bold"), width=75, height=34, command=self._save_trans_settings).grid(row=0, column=3, padx=6, pady=6)

        ctk.CTkLabel(trans_inner, text="LibreTranslate Key:", font=get_font(13)).grid(row=1, column=0, padx=(0, 8), pady=6, sticky="w")
        self.trans_key_entry = ctk.CTkEntry(trans_inner, font=get_font(12), width=280, height=34, show="*")
        self.trans_key_entry.grid(row=1, column=1, columnspan=2, padx=4, pady=6, sticky="w")

        self.trans_key_show_var = tk.BooleanVar(value=False)
        ctk.CTkCheckBox(trans_inner, text="표시", font=get_font(12), variable=self.trans_key_show_var, command=self._toggle_trans_key_visibility).grid(row=1, column=3, padx=6, pady=6)
        self._update_trans_key_state()

        # 7. 클라우드 백업 동기화
        self._build_backup_sync_section(body)

        # 8. 로그 폴더 카드
        log_card = CardFrame(body, title="📁 실행 로그 파일")
        log_card.pack(fill="x", padx=8, pady=6)

        log_inner = ctk.CTkFrame(log_card, fg_color="transparent")
        log_inner.pack(fill="x", padx=12, pady=10)

        ctk.CTkButton(log_inner, text="📂 로그 폴더 열기", font=get_font(12), height=34, command=self._open_log_folder).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(log_inner, text="logs/ 폴더에 날짜별 실행 로그가 누적 기록됩니다.", font=get_font(12), text_color=COLOR_SECONDARY_FG).pack(side="left", padx=4)

    def _on_app_theme_changed(self, choice: str):
        """CustomTkinter 테마 변경 콜백."""
        ctk.set_appearance_mode(choice)
        self.service.config["appearance_mode"] = choice
        try:
            self.service.config_manager.save_config(self.service.config)
        except Exception:
            pass
        self.app._setup_styles()
