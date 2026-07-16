from __future__ import annotations

import os
import hashlib
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from websync.integrations.calibre import CalibreManager
from websync.core.paths import resolve_path
from websync.upload.uploader import X3Uploader, normalize_device_host
from websync.scheduler.manager import SchedulerManager
from websync.integrations.notifier import ToastNotifier
from websync.pipeline.service import SyncService
from websync.core.logger import get_log_dir
from websync.config.exceptions import ConfigSaveError
from websync.gui.widgets import (
    BG_COLOR, FG_COLOR, ACCENT_COLOR, SECONDARY_BG, TEXT_BG, GREEN_COLOR, RED_COLOR, YELLOW_COLOR, HINT_COLOR,
    center_window, setup_dialog
)
from websync.gui.tab_sync import SyncTab
from websync.gui.tab_calibre import CalibreTab
from websync.gui.tab_history import HistoryTab
from websync.gui.tab_device_files import DeviceFilesTab
from websync.gui.tab_settings import SettingsTab
from websync.gui.bottom_bar import BottomBar


class AppLayoutMixin:
    def _preferred_window_size(self) -> tuple[int, int]:
        """디스플레이 배율/해상도에 맞는 초기 창 크기."""
        try:
            sw = int(self.root.winfo_screenwidth())
            sh = int(self.root.winfo_screenheight())
        except Exception:
            return 920, 820
        # 150% 배율 노트북에서도 하단 버튼+로그가 보이도록 여유 확보
        width = max(860, min(1100, int(sw * 0.58)))
        height = max(760, min(980, int(sh * 0.82)))
        return width, height

    def _finalize_layout(self, width: int, height: int) -> None:
        """창 배치 후 하단 패널 최소 높이를 보장한다."""
        center_window(self.root, width, height)
        self.root.update_idletasks()
        self._ensure_bottom_pane_visible()

    def _ensure_bottom_pane_visible(self) -> None:
        """세로 분할창에서 즉시 동기화 버튼이 가려지지 않도록 sash 위치를 1회 조정."""
        if self._bottom_pane_adjusted:
            return
        try:
            self.root.update_idletasks()
            total_h = int(self.main_paned.winfo_height())
            if total_h <= 1:
                self.root.after(50, self._ensure_bottom_pane_visible)
                return
            # 버튼 2줄 + 진행바 + 로그 영역 최소 확보 (고 DPI 여유 포함)
            min_bottom = 220
            target_bottom = max(min_bottom, int(total_h * 0.30))
            sash_y = max(180, total_h - target_bottom)
            self.main_paned.sashpos(0, sash_y)
            self._bottom_pane_adjusted = True
        except Exception:
            pass

    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')

        self.root.configure(bg=BG_COLOR)
        self.style.configure(".", background=BG_COLOR, foreground=FG_COLOR, font=("Malgun Gothic", 9))
        self.style.configure("TFrame", background=BG_COLOR)
        self.style.configure("TNotebook", background=BG_COLOR, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=SECONDARY_BG, foreground=FG_COLOR, padding=[12, 6], font=("Malgun Gothic", 9, "bold"))
        self.style.map("TNotebook.Tab",
            background=[("selected", BG_COLOR)],
            foreground=[("selected", ACCENT_COLOR)]
        )
        self.style.configure("TLabelframe", background=BG_COLOR, foreground=ACCENT_COLOR, bordercolor=SECONDARY_BG)
        self.style.configure("TLabelframe.Label", background=BG_COLOR, foreground=ACCENT_COLOR, font=("Malgun Gothic", 10, "bold"))
        self.style.configure("TLabel", background=BG_COLOR, foreground=FG_COLOR)
        
        # 버튼 스타일
        self.style.configure("TButton", background=SECONDARY_BG, foreground=FG_COLOR, bordercolor=SECONDARY_BG, relief="flat", padding=5)
        self.style.map("TButton",
            background=[("active", ACCENT_COLOR), ("disabled", SECONDARY_BG)],
            foreground=[("active", "#ffffff"), ("disabled", "#adb5bd")]
        )
        
        # 입력 필드 및 스핀박스
        self.style.configure("TEntry", fieldbackground=TEXT_BG, foreground=FG_COLOR, insertcolor=FG_COLOR, bordercolor=SECONDARY_BG)
        self.style.configure("TCombobox", fieldbackground=TEXT_BG, foreground=FG_COLOR, background=SECONDARY_BG, arrowcolor=FG_COLOR, bordercolor=SECONDARY_BG)
        self.style.configure("TSpinbox", fieldbackground=TEXT_BG, foreground=FG_COLOR, background=SECONDARY_BG, arrowcolor=FG_COLOR, bordercolor=SECONDARY_BG)

        # 트리뷰
        self.style.configure("Treeview", background=TEXT_BG, fieldbackground=TEXT_BG, foreground=FG_COLOR, bordercolor=SECONDARY_BG, rowheight=24)
        self.style.map("Treeview", background=[("selected", ACCENT_COLOR)], foreground=[("selected", "#ffffff")])
        self.style.configure("Treeview.Heading", background=SECONDARY_BG, foreground=FG_COLOR, bordercolor=SECONDARY_BG, font=("Malgun Gothic", 9, "bold"))
        self.style.configure("TProgressbar", troughcolor=SECONDARY_BG, background=ACCENT_COLOR, thickness=8)
        self.style.configure("TCheckbutton", background=BG_COLOR, foreground=FG_COLOR)

    def _build_ui(self):
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.main_paned.pack(fill="both", expand=True, padx=10, pady=10)

        tab_container = ttk.Frame(self.main_paned)
        self.main_paned.add(tab_container, weight=3)

        self.notebook = ttk.Notebook(tab_container)
        self.notebook.pack(fill="both", expand=True)

        # 탭 컴포넌트 생성 및 추가
        self.tab_sync = SyncTab(self.notebook, self)
        self.tab_calibre = CalibreTab(self.notebook, self)
        self.tab_history = HistoryTab(self.notebook, self)
        self.tab_device_files = DeviceFilesTab(self.notebook, self)
        self.tab_settings = SettingsTab(self.notebook, self)

        self.notebook.add(self.tab_sync, text=" 뉴스 동기화 ")
        self.notebook.add(self.tab_calibre, text=" Calibre 서재 ")
        self.notebook.add(self.tab_history, text=" 📋 동기화 이력 ")
        self.notebook.add(self.tab_device_files, text=" 📁 기기 파일 ")
        self.notebook.add(self.tab_settings, text=" ⚙️ 고급 & 서버 설정 ")

        # 하단 바 (즉시 동기화 / 프리뷰 / 로그)
        bottom_container = ttk.Frame(self.main_paned)
        self.main_paned.add(bottom_container, weight=1)
        # weight만으로는 고 DPI에서 하단이 거의 사라질 수 있어 minsize 지정
        try:
            self.main_paned.paneconfigure(bottom_container, minsize=200, weight=1)
            self.main_paned.paneconfigure(tab_container, minsize=240, weight=3)
        except tk.TclError:
            pass

        self.bottom_bar = BottomBar(bottom_container, self)
        # pack 누락 시 동기화 버튼·로그 전체가 아예 안 보임
        self.bottom_bar.pack(fill="both", expand=True)

