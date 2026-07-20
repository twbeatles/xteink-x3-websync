"""하단 바 및 프로그램 로그 영역 컴포넌트"""
import tkinter as tk
from tkinter import ttk

from websync.gui.widgets import (
    TEXT_BG, FG_COLOR,
    bind_text_mousewheel
)


class BottomBar(ttk.Frame):
    """즉시 동기화, 프리뷰 제어, 진행도 표시, 로그 출력을 담당하는 하단 패널"""

    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        self._build_ui()

    def _build_ui(self):
        # 고 DPI(150% 등)에서 가로 한 줄이 잘리지 않도록 버튼을 세로로 배치
        sync_run_frame = ttk.Frame(self)
        sync_run_frame.pack(fill="x", padx=5, pady=2)

        self.sync_now_btn = ttk.Button(
            sync_run_frame,
            text="🚀 즉시 전체 뉴스 스크래핑 및 X3 동기화 실행",
            command=self.app._run_immediate_sync,
        )
        self.sync_now_btn.pack(fill="x", pady=(2, 1))

        self.preview_btn = ttk.Button(
            sync_run_frame,
            text="🔍 뉴스 프리뷰 (선택 동기화)",
            command=self.app.tab_sync.open_preview_window,
        )
        self.preview_btn.pack(fill="x", pady=(1, 2))

        # 진행률 표시바
        self.progress_bar = ttk.Progressbar(
            self, orient="horizontal", mode="determinate", style="TProgressbar"
        )
        self.progress_bar.pack(fill="x", padx=5, pady=(0, 2))

        log_frame = ttk.LabelFrame(self, text=" 프로그램 상태 및 동기화 로그 ")
        log_frame.pack(fill="both", expand=True, padx=5, pady=(2, 5))

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill="both", expand=True, padx=8, pady=8)

        # height를 너무 크게 두지 않아 고 DPI에서도 버튼 영역이 우선 확보되게 함
        self.log_txt = tk.Text(
            log_inner,
            height=4,
            bg=TEXT_BG,
            fg=FG_COLOR,
            insertbackground=FG_COLOR,
            font=("Malgun Gothic", 9),
            wrap="word",
        )
        self.log_txt.pack(side="left", fill="both", expand=True)

        log_scroll = ttk.Scrollbar(log_inner, orient="vertical", command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_txt.config(state="disabled")
        bind_text_mousewheel(self.log_txt)
