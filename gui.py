import os
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from calibre import CalibreManager
from uploader import X3Uploader
from scheduler import SchedulerManager
from notifier import ToastNotifier
from service import SyncService
from opds_server import OPDSServer
from watcher import CalibreWatcher
from web_api import WebDashboard
from logger import get_log_dir

class SyncAppGui:
    """Tkinter를 기반으로 탭형 인터페이스를 제공하고 비즈니스 흐름을 연동하는 클래스"""
    def __init__(self, service: SyncService):
        self.service = service
        self.scheduler = SchedulerManager()
        self.calibre = CalibreManager(self.service.config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"))

        # 서버 인스턴스
        self._opds_server: OPDSServer | None = None
        self._web_dashboard: WebDashboard | None = None
        self._calibre_watcher: CalibreWatcher | None = None

        self.root = tk.Tk()
        self.root.title("Xteink X3 WebSync Manager")
        self.root.geometry("860x760")
        self.root.resizable(True, True)

        self._setup_styles()
        self._build_ui()
        self._load_config_to_ui()

        # 종료 시 서버 정리
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------
    # 스타일 설정
    # ------------------------------------------------------------------
    def _setup_styles(self):
        self.style = ttk.Style()
        self.style.theme_use('clam')

        # 라이트 테마 색상 정의 (Clean Light Theme)
        self.BG_COLOR      = "#f8f9fa" # 연한 회색 배경
        self.FG_COLOR      = "#212529" # 어두운 텍스트
        self.ACCENT_COLOR  = "#0d6efd" # 파란색 포인트
        self.SECONDARY_BG  = "#e9ecef" # 비활성 탭 및 서브 프레임 배경
        self.TEXT_BG       = "#ffffff" # 입력 필드, 리스트 박스 배경
        self.GREEN_COLOR   = "#198754" # 상태 양호 초록색
        self.RED_COLOR     = "#dc3545" # 에러 빨간색
        self.YELLOW_COLOR  = "#fd7e14" # 미확인/대기 주황색

        self.root.configure(bg=self.BG_COLOR)
        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, font=("Malgun Gothic", 9))
        self.style.configure("TFrame", background=self.BG_COLOR)
        self.style.configure("TNotebook", background=self.BG_COLOR, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=self.SECONDARY_BG, foreground=self.FG_COLOR, padding=[12, 6], font=("Malgun Gothic", 9, "bold"))
        self.style.map("TNotebook.Tab",
            background=[("selected", self.BG_COLOR)],
            foreground=[("selected", self.ACCENT_COLOR)]
        )
        self.style.configure("TLabelframe", background=self.BG_COLOR, foreground=self.ACCENT_COLOR, bordercolor=self.SECONDARY_BG)
        self.style.configure("TLabelframe.Label", background=self.BG_COLOR, foreground=self.ACCENT_COLOR, font=("Malgun Gothic", 10, "bold"))
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        
        # 버튼 스타일 정의
        self.style.configure("TButton", background=self.SECONDARY_BG, foreground=self.FG_COLOR, bordercolor=self.SECONDARY_BG, relief="flat", padding=5)
        self.style.map("TButton",
            background=[("active", self.ACCENT_COLOR), ("disabled", self.SECONDARY_BG)],
            foreground=[("active", "#ffffff"), ("disabled", "#adb5bd")]
        )
        
        # 입력 필드, 드롭다운, 스핀박스 스타일 강제 재정의 (가독성 문제 완전 해결)
        self.style.configure("TEntry", fieldbackground=self.TEXT_BG, foreground=self.FG_COLOR, insertcolor=self.FG_COLOR, bordercolor=self.SECONDARY_BG)
        self.style.configure("TCombobox", fieldbackground=self.TEXT_BG, foreground=self.FG_COLOR, background=self.SECONDARY_BG, arrowcolor=self.FG_COLOR, bordercolor=self.SECONDARY_BG)
        self.style.configure("TSpinbox", fieldbackground=self.TEXT_BG, foreground=self.FG_COLOR, background=self.SECONDARY_BG, arrowcolor=self.FG_COLOR, bordercolor=self.SECONDARY_BG)

        # 트리뷰 스타일 정의
        self.style.configure("Treeview", background=self.TEXT_BG, fieldbackground=self.TEXT_BG, foreground=self.FG_COLOR, bordercolor=self.SECONDARY_BG, rowheight=24)
        self.style.map("Treeview", background=[("selected", self.ACCENT_COLOR)], foreground=[("selected", "#ffffff")])
        self.style.configure("Treeview.Heading", background=self.SECONDARY_BG, foreground=self.FG_COLOR, bordercolor=self.SECONDARY_BG, font=("Malgun Gothic", 9, "bold"))
        self.style.configure("TProgressbar", troughcolor=self.SECONDARY_BG, background=self.ACCENT_COLOR, thickness=8)


    # ------------------------------------------------------------------
    # UI 빌드
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        self.tab_sync    = ttk.Frame(self.notebook)
        self.tab_calibre = ttk.Frame(self.notebook)
        self.tab_history = ttk.Frame(self.notebook)
        self.tab_server  = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_sync,    text=" 뉴스 동기화 및 일반설정 ")
        self.notebook.add(self.tab_calibre, text=" Calibre 서재 연동 ")
        self.notebook.add(self.tab_history, text=" 📋 동기화 이력 ")
        self.notebook.add(self.tab_server,  text=" ⚙️ 서버 & 고급 설정 ")

        self._build_tab_sync()
        self._build_tab_calibre()
        self._build_tab_history()
        self._build_tab_server()
        self._build_bottom_bar()

    # ── 탭 1: 뉴스 동기화 ────────────────────────────────────────────
    def _build_tab_sync(self):
        # 기기 및 경로
        settings_frame = ttk.LabelFrame(self.tab_sync, text=" 기기 및 경로 설정 ")
        settings_frame.pack(fill="x", padx=15, pady=8)

        ttk.Label(settings_frame, text="X3 주소 (IP/호스트):").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.ip_entry = ttk.Entry(settings_frame, width=22, font=("Consolas", 10))
        self.ip_entry.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        self.test_conn_btn = ttk.Button(settings_frame, text="연결 확인", command=self._test_connection)
        self.test_conn_btn.grid(row=0, column=2, padx=5, pady=6)
        self.conn_status_label = ttk.Label(settings_frame, text="미확인", foreground=self.YELLOW_COLOR)
        self.conn_status_label.grid(row=0, column=3, padx=10, pady=6, sticky="w")

        ttk.Label(settings_frame, text="출력 저장 폴더:").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.dir_entry = ttk.Entry(settings_frame, width=45)
        self.dir_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=6, sticky="we")
        ttk.Button(settings_frame, text="폴더 선택", command=self._browse_directory).grid(row=1, column=3, padx=5, pady=6)
        ttk.Button(settings_frame, text="📂 열기", command=self._open_output_folder).grid(row=1, column=4, padx=5, pady=6)

        # 폰트 설정
        font_frame = ttk.LabelFrame(self.tab_sync, text=" 한국어 가독성 스타일 최적화 (EPUB 포맷팅) ")
        font_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(font_frame, text="폰트:").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.font_cb = ttk.Combobox(font_frame, values=["serif", "sans-serif", "KoPubWorldBatang", "NanumGothic", "Malgun Gothic"], width=15)
        self.font_cb.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        self.font_cb.set("serif")

        ttk.Label(font_frame, text="글자 크기:").grid(row=0, column=2, padx=15, pady=6, sticky="w")
        self.font_size_sp = ttk.Spinbox(font_frame, from_=10, to=30, width=5)
        self.font_size_sp.grid(row=0, column=3, padx=5, pady=6, sticky="w")
        self.font_size_sp.set("16")

        ttk.Label(font_frame, text="줄 간격:").grid(row=0, column=4, padx=15, pady=6, sticky="w")
        self.line_height_sp = ttk.Spinbox(font_frame, from_=1.0, to=3.0, increment=0.1, width=5)
        self.line_height_sp.grid(row=0, column=5, padx=5, pady=6, sticky="w")
        self.line_height_sp.set("1.7")

        self.cover_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(font_frame, text="EPUB 표지 자동 생성", variable=self.cover_var).grid(row=0, column=6, padx=10, pady=6)

        # 사이트 관리
        sites_frame = ttk.LabelFrame(self.tab_sync, text=" 동기화 대상 사이트 관리 ")
        sites_frame.pack(fill="both", expand=True, padx=15, pady=5)

        columns = ("name", "type", "enabled", "url")
        self.tree = ttk.Treeview(sites_frame, columns=columns, show="headings")
        self.tree.heading("name", text="사이트 이름")
        self.tree.heading("type", text="유형")
        self.tree.heading("enabled", text="활성화")
        self.tree.heading("url", text="URL")
        self.tree.column("name", width=140, anchor="w")
        self.tree.column("type", width=60, anchor="center")
        self.tree.column("enabled", width=55, anchor="center")
        self.tree.column("url", width=390, anchor="w")
        self.tree.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        scrollbar = ttk.Scrollbar(sites_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=8)

        btn_frame = ttk.Frame(sites_frame)
        btn_frame.pack(side="bottom", fill="x", padx=10, pady=(0, 8))
        ttk.Button(btn_frame, text="사이트 추가", command=self._add_site_popup).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="사이트 수정", command=self._edit_site_popup).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="선택 삭제", command=self._delete_site).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="활성 토글", command=self._toggle_site_enabled).pack(side="left", padx=3)

        # 하단 그리드: 직접 전송 + 스케줄러
        bottom_grid = ttk.Frame(self.tab_sync)
        bottom_grid.pack(fill="x", padx=15, pady=5)
        bottom_grid.columnconfigure(0, weight=1)
        bottom_grid.columnconfigure(1, weight=1)

        upload_frame = ttk.LabelFrame(bottom_grid, text=" 로컬 파일 X3 직접 전송 ")
        upload_frame.grid(row=0, column=0, padx=(0, 5), sticky="nswe")
        self.file_entry = ttk.Entry(upload_frame, width=28)
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
        self.sched_status_label = ttk.Label(scheduler_frame, text="스케줄 확인 중...", font=("Malgun Gothic", 8))
        self.sched_status_label.grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 6), sticky="w")

    # ── 탭 2: Calibre 서재 ──────────────────────────────────────────
    def _build_tab_calibre(self):
        calibre_top_frame = ttk.LabelFrame(self.tab_calibre, text=" Calibre 연동 설정 ")
        calibre_top_frame.pack(fill="x", padx=15, pady=10)

        ttk.Label(calibre_top_frame, text="calibredb.exe 경로:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.calibre_entry = ttk.Entry(calibre_top_frame, width=50)
        self.calibre_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(calibre_top_frame, text="찾아보기", command=self._browse_calibredb).grid(row=0, column=2, padx=5, pady=8)
        self.calibre_conn_btn = ttk.Button(calibre_top_frame, text="연결 확인 & 서재 로드", command=self._test_and_load_calibre)
        self.calibre_conn_btn.grid(row=0, column=3, padx=10, pady=8)

        calibre_list_frame = ttk.LabelFrame(self.tab_calibre, text=" 내 Calibre 서재 도서 목록 ")
        calibre_list_frame.pack(fill="both", expand=True, padx=15, pady=5)

        c_columns = ("id", "title", "authors", "formats")
        self.calibre_tree = ttk.Treeview(calibre_list_frame, columns=c_columns, show="headings")
        self.calibre_tree.heading("id", text="ID")
        self.calibre_tree.heading("title", text="도서 제목")
        self.calibre_tree.heading("authors", text="저자")
        self.calibre_tree.heading("formats", text="보유 포맷")
        self.calibre_tree.column("id", width=50, anchor="center")
        self.calibre_tree.column("title", width=320, anchor="w")
        self.calibre_tree.column("authors", width=180, anchor="w")
        self.calibre_tree.column("formats", width=120, anchor="center")
        self.calibre_tree.pack(side="left", fill="both", expand=True, padx=10, pady=10)

        c_scrollbar = ttk.Scrollbar(calibre_list_frame, orient="vertical", command=self.calibre_tree.yview)
        self.calibre_tree.configure(yscrollcommand=c_scrollbar.set)
        c_scrollbar.pack(side="right", fill="y", padx=(0, 10), pady=10)

        calibre_action_frame = ttk.Frame(self.tab_calibre)
        calibre_action_frame.pack(fill="x", padx=15, pady=10)
        self.calibre_send_btn = ttk.Button(calibre_action_frame, text="★ 선택한 도서 X3 기기로 즉시 전송 (다중 선택 가능)", command=self._send_calibre_books)
        self.calibre_send_btn.pack(fill="x", pady=5)

    # ── 탭 3: 동기화 이력 ───────────────────────────────────────────
    def _build_tab_history(self):
        ctrl_frame = ttk.Frame(self.tab_history)
        ctrl_frame.pack(fill="x", padx=15, pady=8)
        ttk.Button(ctrl_frame, text="🔄 이력 새로고침", command=self._refresh_history).pack(side="left", padx=3)
        ttk.Button(ctrl_frame, text="🗑 선택 항목 삭제 (재전송 허용)", command=self._delete_history_entry).pack(side="left", padx=3)
        ttk.Button(ctrl_frame, text="⚠️ 전체 이력 초기화", command=self._clear_all_history).pack(side="left", padx=3)
        self.history_count_label = ttk.Label(ctrl_frame, text="", foreground=self.YELLOW_COLOR)
        self.history_count_label.pack(side="right", padx=10)

        hist_frame = ttk.LabelFrame(self.tab_history, text=" 전송 완료된 포스트 목록 (최신 200건) ")
        hist_frame.pack(fill="both", expand=True, padx=15, pady=5)

        h_columns = ("site", "title", "synced_at", "url")
        self.hist_tree = ttk.Treeview(hist_frame, columns=h_columns, show="headings", selectmode="extended")
        self.hist_tree.heading("site", text="사이트")
        self.hist_tree.heading("title", text="제목")
        self.hist_tree.heading("synced_at", text="전송 시각")
        self.hist_tree.heading("url", text="URL")
        self.hist_tree.column("site", width=120, anchor="w")
        self.hist_tree.column("title", width=280, anchor="w")
        self.hist_tree.column("synced_at", width=150, anchor="center")
        self.hist_tree.column("url", width=250, anchor="w")
        self.hist_tree.pack(side="left", fill="both", expand=True, padx=10, pady=8)

        h_scroll = ttk.Scrollbar(hist_frame, orient="vertical", command=self.hist_tree.yview)
        self.hist_tree.configure(yscrollcommand=h_scroll.set)
        h_scroll.pack(side="right", fill="y", padx=(0, 10), pady=8)

    # ── 탭 4: 서버 & 고급 설정 ────────────────────────────────────
    def _build_tab_server(self):
        # OPDS 서버
        opds_frame = ttk.LabelFrame(self.tab_server, text=" 📡 OPDS 카탈로그 서버 ")
        opds_frame.pack(fill="x", padx=15, pady=10)
        ttk.Label(opds_frame, text="포트:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.opds_port_sp = ttk.Spinbox(opds_frame, from_=1024, to=65535, width=6)
        self.opds_port_sp.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.opds_port_sp.set("8765")
        self.opds_start_btn = ttk.Button(opds_frame, text="▶ 서버 시작", command=self._toggle_opds)
        self.opds_start_btn.grid(row=0, column=2, padx=5, pady=8)
        self.opds_status_label = ttk.Label(opds_frame, text="중지됨", foreground=self.RED_COLOR)
        self.opds_status_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.opds_url_label = ttk.Label(opds_frame, text="", foreground=self.ACCENT_COLOR, cursor="hand2")
        self.opds_url_label.grid(row=0, column=4, padx=10, pady=8, sticky="w")
        self.opds_url_label.bind("<Button-1>", lambda e: self._open_url(self.opds_url_label.cget("text")))
        ttk.Label(opds_frame, text="X3 기기 OPDS 클라이언트에서 위 주소로 접속하면 생성된 EPUB 목록을 바로 다운로드할 수 있습니다.", font=("Malgun Gothic", 8), foreground="#a6adc8").grid(row=1, column=0, columnspan=5, padx=10, pady=(0, 8), sticky="w")

        # 웹 대시보드
        web_frame = ttk.LabelFrame(self.tab_server, text=" 🌐 웹 대시보드 ")
        web_frame.pack(fill="x", padx=15, pady=5)
        ttk.Label(web_frame, text="포트:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.web_port_sp = ttk.Spinbox(web_frame, from_=1024, to=65535, width=6)
        self.web_port_sp.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.web_port_sp.set("8766")
        self.web_start_btn = ttk.Button(web_frame, text="▶ 서버 시작", command=self._toggle_web)
        self.web_start_btn.grid(row=0, column=2, padx=5, pady=8)
        self.web_status_label = ttk.Label(web_frame, text="중지됨", foreground=self.RED_COLOR)
        self.web_status_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.web_url_label = ttk.Label(web_frame, text="", foreground=self.ACCENT_COLOR, cursor="hand2")
        self.web_url_label.grid(row=0, column=4, padx=10, pady=8, sticky="w")
        self.web_url_label.bind("<Button-1>", lambda e: self._open_url(self.web_url_label.cget("text")))

        # Calibre Watch
        watch_frame = ttk.LabelFrame(self.tab_server, text=" 👁 Calibre 서재 자동 감시 (새 파일 추가 시 자동 전송) ")
        watch_frame.pack(fill="x", padx=15, pady=5)
        ttk.Label(watch_frame, text="감시 폴더:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.watch_dir_entry = ttk.Entry(watch_frame, width=45)
        self.watch_dir_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(watch_frame, text="폴더 선택", command=self._browse_watch_dir).grid(row=0, column=2, padx=5, pady=8)
        self.watch_start_btn = ttk.Button(watch_frame, text="▶ 감시 시작", command=self._toggle_watch)
        self.watch_start_btn.grid(row=0, column=3, padx=5, pady=8)
        self.watch_status_label = ttk.Label(watch_frame, text="감시 중지됨", foreground=self.RED_COLOR)
        self.watch_status_label.grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="w")

        # AI 요약 설정
        ai_frame = ttk.LabelFrame(self.tab_server, text=" 🤖 AI 기사 요약 설정 (선택) ")
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

        # 번역 설정
        trans_frame = ttk.LabelFrame(self.tab_server, text=" 🌐 번역 설정 (선택) ")
        trans_frame.pack(fill="x", padx=15, pady=5)

        self.trans_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(trans_frame, text="번역 활성화", variable=self.trans_enabled_var).grid(row=0, column=0, padx=10, pady=6, sticky="w")

        ttk.Label(trans_frame, text="프로바이더:").grid(row=0, column=1, padx=10, pady=6, sticky="w")
        self.trans_provider_cb = ttk.Combobox(trans_frame, values=["googletrans", "libretranslate"], width=14, state="readonly")
        self.trans_provider_cb.grid(row=0, column=2, padx=5, pady=6)
        self.trans_provider_cb.set("googletrans")

        ttk.Button(trans_frame, text="저장", command=self._save_trans_settings).grid(row=0, column=3, padx=10, pady=6)

        # 로그 폴더 열기
        log_frame = ttk.LabelFrame(self.tab_server, text=" 📂 로그 파일 ")
        log_frame.pack(fill="x", padx=15, pady=5)
        ttk.Button(log_frame, text="📂 로그 폴더 열기", command=self._open_log_folder).pack(side="left", padx=10, pady=8)
        ttk.Label(log_frame, text="logs/ 폴더에 날짜별 sync_YYYY-MM-DD.log 파일이 저장됩니다.", font=("Malgun Gothic", 8), foreground="#a6adc8").pack(side="left", padx=5, pady=8)

    # ── 하단 공통 바 ──────────────────────────────────────────────
    def _build_bottom_bar(self):
        sync_run_frame = ttk.Frame(self.root)
        sync_run_frame.pack(fill="x", padx=15, pady=2)

        self.sync_now_btn = ttk.Button(sync_run_frame, text="🚀 즉시 전체 뉴스 스크래핑 및 X3 동기화 실행", command=self._run_immediate_sync)
        self.sync_now_btn.pack(fill="x", pady=3)

        # 진행률 표시바
        self.progress_bar = ttk.Progressbar(self.root, orient="horizontal", mode="determinate", style="TProgressbar")
        self.progress_bar.pack(fill="x", padx=15, pady=(0, 2))

        log_frame = ttk.LabelFrame(self.root, text=" 프로그램 상태 및 동기화 로그 ")
        log_frame.pack(fill="both", expand=False, padx=15, pady=(2, 10))

        self.log_txt = tk.Text(log_frame, height=6, bg=self.TEXT_BG, fg=self.FG_COLOR, insertbackground=self.FG_COLOR, font=("Consolas", 9))
        self.log_txt.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_txt.config(state="disabled")

    # ------------------------------------------------------------------
    # 내부 유틸
    # ------------------------------------------------------------------
    def _log_message(self, message: str):
        self.log_txt.config(state="normal")
        self.log_txt.insert(tk.END, message + "\n")
        self.log_txt.see(tk.END)
        self.log_txt.config(state="disabled")

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.progress_bar["maximum"] = total
            self.progress_bar["value"] = current
        else:
            self.progress_bar["value"] = 0

    def _open_url(self, url: str):
        if url:
            try:
                import webbrowser
                webbrowser.open(url)
            except Exception:
                pass

    # ------------------------------------------------------------------
    # 설정 로드 / 저장
    # ------------------------------------------------------------------
    def _load_config_to_ui(self):
        config = self.service.config
        self.ip_entry.insert(0, config.get("x3_ip", "crosspoint.local"))
        self.dir_entry.insert(0, config.get("output_dir", "./output"))
        self.calibre_entry.insert(0, config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"))
        self.font_cb.set(config.get("font_family", "serif"))
        self.font_size_sp.set(str(config.get("font_size", 16)))
        self.line_height_sp.set(str(config.get("line_height", 1.7)))
        self.cover_var.set(config.get("epub_cover", True))

        sched_conf = config.get("schedule", {})
        self.hour_cb.set(sched_conf.get("hour", "07"))
        self.min_cb.set(sched_conf.get("minute", "00"))

        # OPDS / Web 포트
        opds_conf = config.get("opds_server", {})
        self.opds_port_sp.set(str(opds_conf.get("port", 8765)))

        web_conf = config.get("web_dashboard", {})
        self.web_port_sp.set(str(web_conf.get("port", 8766)))

        # Calibre Watch 폴더
        watch_conf = config.get("calibre_watch", {})
        self.watch_dir_entry.insert(0, watch_conf.get("watch_dir", ""))

        # AI 요약
        ai_conf = config.get("ai_summary", {})
        self.ai_enabled_var.set(ai_conf.get("enabled", False))
        self.ai_provider_cb.set(ai_conf.get("provider", "openai"))
        self.ai_key_entry.insert(0, ai_conf.get("api_key", ""))

        # 번역
        trans_conf = config.get("translation", {})
        self.trans_enabled_var.set(trans_conf.get("enabled", False))
        self.trans_provider_cb.set(trans_conf.get("provider", "googletrans"))

        self._refresh_site_tree()
        self._refresh_schedule_status()
        self._refresh_history()
        threading.Thread(target=self._test_and_load_calibre, kwargs={"silent": True}, daemon=True).start()

    def _save_ui_settings(self):
        config = self.service.config
        config["x3_ip"] = self.ip_entry.get().strip()
        config["output_dir"] = self.dir_entry.get().strip()
        config["calibre_path"] = self.calibre_entry.get().strip()
        config["font_family"] = self.font_cb.get()
        config["epub_cover"] = self.cover_var.get()
        try:
            config["font_size"] = int(self.font_size_sp.get())
        except ValueError:
            config["font_size"] = 16
        try:
            config["line_height"] = float(self.line_height_sp.get())
        except ValueError:
            config["line_height"] = 1.7
        config["schedule"]["hour"] = self.hour_cb.get()
        config["schedule"]["minute"] = self.min_cb.get()
        self.service.config_manager.save_config(config)
        self.calibre.calibre_path = config["calibre_path"]

    def _save_ai_settings(self):
        config = self.service.config
        config["ai_summary"] = {
            "enabled": self.ai_enabled_var.get(),
            "provider": self.ai_provider_cb.get(),
            "api_key": self.ai_key_entry.get().strip(),
            "model": config.get("ai_summary", {}).get("model", "gpt-4o-mini"),
            "ollama_host": config.get("ai_summary", {}).get("ollama_host", "http://localhost:11434"),
        }
        self.service.config_manager.save_config(config)
        messagebox.showinfo("저장 완료", "AI 요약 설정이 저장되었습니다.")

    def _save_trans_settings(self):
        config = self.service.config
        config["translation"] = {
            "enabled": self.trans_enabled_var.get(),
            "provider": self.trans_provider_cb.get(),
            "libretranslate_host": config.get("translation", {}).get("libretranslate_host", "http://localhost:5000"),
            "libretranslate_api_key": config.get("translation", {}).get("libretranslate_api_key", ""),
        }
        self.service.config_manager.save_config(config)
        messagebox.showinfo("저장 완료", "번역 설정이 저장되었습니다.")

    # ------------------------------------------------------------------
    # 파일/폴더 탐색
    # ------------------------------------------------------------------
    def _browse_directory(self):
        d = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if d:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, d)
            self._save_ui_settings()

    def _browse_file(self):
        f = filedialog.askopenfilename(title="X3로 전송할 파일 선택", filetypes=[("eBook files", "*.epub;*.pdf;*.txt;*.mobi"), ("All files", "*.*")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)

    def _browse_calibredb(self):
        f = filedialog.askopenfilename(title="calibredb.exe 실행파일 찾기", filetypes=[("Executable", "calibredb.exe"), ("All files", "*.*")])
        if f:
            self.calibre_entry.delete(0, tk.END)
            self.calibre_entry.insert(0, f)
            self._save_ui_settings()

    def _browse_watch_dir(self):
        d = filedialog.askdirectory(title="감시할 Calibre 라이브러리 폴더 선택")
        if d:
            self.watch_dir_entry.delete(0, tk.END)
            self.watch_dir_entry.insert(0, d)

    def _open_output_folder(self):
        """출력 폴더를 탐색기로 엽니다."""
        folder = self.dir_entry.get().strip() or "./output"
        folder = os.path.abspath(folder)
        os.makedirs(folder, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif os.sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("오류", f"폴더를 열 수 없습니다: {e}")

    def _open_log_folder(self):
        """로그 폴더를 탐색기로 엽니다."""
        folder = get_log_dir()
        os.makedirs(folder, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif os.sys.platform == "darwin":
                subprocess.Popen(["open", folder])
            else:
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("오류", f"로그 폴더를 열 수 없습니다: {e}")

    # ------------------------------------------------------------------
    # 연결 / 직접 전송
    # ------------------------------------------------------------------
    def _test_connection(self):
        ip = self.ip_entry.get().strip()
        self.conn_status_label.config(text="연결 중...", foreground=self.YELLOW_COLOR)
        self.root.update_idletasks()
        if X3Uploader(ip).test_connection():
            self.conn_status_label.config(text="연결 성공 ✅", foreground=self.GREEN_COLOR)
        else:
            self.conn_status_label.config(text="연결 실패 ❌", foreground=self.RED_COLOR)

    def _direct_upload(self):
        file_path = self.file_entry.get().strip()
        ip = self.ip_entry.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("경고", "올바른 파일 경로를 지정해 주세요.")
            return
        self._save_ui_settings()
        self._log_message(f"📡 로컬 파일 직접 전송 중: {os.path.basename(file_path)}")
        self.direct_upload_btn.config(state="disabled")

        def task():
            success = X3Uploader(ip).upload(file_path)
            self.root.after(0, lambda: self._direct_upload_finished(success, file_path))

        threading.Thread(target=task, daemon=True).start()

    def _direct_upload_finished(self, success: bool, file_path: str):
        self.direct_upload_btn.config(state="normal")
        if success:
            self._log_message(f"🎉 파일 전송 성공: {os.path.basename(file_path)}")
            ToastNotifier.show_toast("파일 업로드 성공", f"'{os.path.basename(file_path)}' 전송 완료.")
            messagebox.showinfo("완료", "기기로 전송이 완료되었습니다.")
        else:
            self._log_message(f"❌ 파일 전송 실패: {os.path.basename(file_path)}")
            ToastNotifier.show_toast("파일 업로드 실패", "기기 전송 오류. 연결 상태 확인 요망.", is_error=True)
            messagebox.showerror("오류", "기기로 전송하지 못했습니다.")

    # ------------------------------------------------------------------
    # 스케줄러
    # ------------------------------------------------------------------
    def _register_schedule(self):
        self._save_ui_settings()
        h, m = self.hour_cb.get(), self.min_cb.get()
        if self.scheduler.register_daily_task(h, m):
            messagebox.showinfo("스케줄러", f"매일 {h}:{m}에 백그라운드 동기화 스케줄이 등록되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = True
            self.service.config_manager.save_config(config)
        else:
            messagebox.showerror("스케줄러", "스케줄러 등록에 실패했습니다. 관리자 권한을 확인하세요.")
        self._refresh_schedule_status()

    def _unregister_schedule(self):
        if self.scheduler.unregister_task():
            messagebox.showinfo("스케줄러", "스케줄 작업이 해제되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = False
            self.service.config_manager.save_config(config)
        else:
            messagebox.showwarning("스케줄러", "스케줄 해제에 실패했거나 등록된 작업이 없습니다.")
        self._refresh_schedule_status()

    def _refresh_schedule_status(self):
        status = self.scheduler.get_task_status()
        self.sched_status_label.config(text=f"스케줄러 상태: {status}")

    # ------------------------------------------------------------------
    # Calibre
    # ------------------------------------------------------------------
    def _test_and_load_calibre(self, silent=False):
        self._save_ui_settings()
        self.calibre.calibre_path = self.calibre_entry.get().strip()
        if not silent:
            self._log_message("📚 Calibre 연결 확인 중...")
            self.calibre_conn_btn.config(state="disabled")
        if not self.calibre.test_connection():
            if not silent:
                self._log_message("❌ Calibre 연동 실패: 경로를 확인하세요.")
                messagebox.showerror("Calibre 연동 실패", "calibredb.exe 경로를 찾지 못했습니다.")
                self.calibre_conn_btn.config(state="normal")
            return
        threading.Thread(target=lambda: self.root.after(0, lambda: self._show_calibre_books(self.calibre.list_books(), silent)), daemon=True).start()

    def _show_calibre_books(self, books: list, silent: bool):
        self.calibre_conn_btn.config(state="normal")
        for item in self.calibre_tree.get_children():
            self.calibre_tree.delete(item)
        if not books:
            if not silent:
                self._log_message("⚠️ Calibre 연동 성공했으나 책이 없습니다.")
            return
        for bk in books:
            formats = bk.get("formats", "")
            formats_str = ", ".join(formats) if isinstance(formats, list) else str(formats)
            self.calibre_tree.insert("", "end", iid=str(bk.get("id")), values=(bk.get("id"), bk.get("title"), bk.get("authors", ""), formats_str))
        if not silent:
            self._log_message(f"🎉 Calibre 서재 로드 완료: {len(books)}권")
            ToastNotifier.show_toast("Calibre 연동 성공", f"서재에서 {len(books)}권 불러왔습니다.")

    def _send_calibre_books(self):
        selected_items = self.calibre_tree.selection()
        if not selected_items:
            messagebox.showwarning("선택 누락", "전송할 도서를 선택해 주세요.")
            return
        self._save_ui_settings()
        ip = self.ip_entry.get().strip()
        self.calibre_send_btn.config(state="disabled")
        self._log_message(f"\n=== Calibre 책 {len(selected_items)}권 무선 전송 시작 ===")

        def task():
            success_cnt = 0
            uploader = X3Uploader(ip)
            for item_id in selected_items:
                book_id = int(item_id)
                file_path = self.calibre.get_book_file_path(book_id)
                if not file_path or not os.path.exists(file_path):
                    self.root.after(0, lambda b=book_id: self._log_message(f"❌ [책 ID {b}] 파일 경로 조회 실패"))
                    continue
                self.root.after(0, lambda p=file_path: self._log_message(f"📡 전송 중: {os.path.basename(p)}"))
                if uploader.upload(file_path):
                    self.root.after(0, lambda p=file_path: self._log_message(f"🎉 성공: {os.path.basename(p)}"))
                    success_cnt += 1
                else:
                    self.root.after(0, lambda p=file_path: self._log_message(f"❌ 실패: {os.path.basename(p)}"))
            self.root.after(0, lambda: self._calibre_send_finished(success_cnt, len(selected_items)))

        threading.Thread(target=task, daemon=True).start()

    def _calibre_send_finished(self, success_cnt: int, total_cnt: int):
        self.calibre_send_btn.config(state="normal")
        self._log_message(f"=== Calibre 도서 전송 종료: {success_cnt}/{total_cnt} 성공 ===\n")
        if success_cnt > 0:
            ToastNotifier.show_toast("Calibre 도서 동기화", f"{success_cnt}권 전송 완료.")
            messagebox.showinfo("완료", f"{success_cnt}권의 책이 전송되었습니다.")
        else:
            messagebox.showerror("오류", "전송에 실패했습니다. 기기 연결 상태를 확인하세요.")

    # ------------------------------------------------------------------
    # 사이트 관리
    # ------------------------------------------------------------------
    def _refresh_site_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for idx, site in enumerate(self.service.config.get("sites", [])):
            self.tree.insert("", "end", iid=str(idx), values=(
                site.get("name"), site.get("type", "css").upper(),
                "V" if site.get("enabled", True) else "-",
                site.get("url")
            ))

    def _toggle_site_enabled(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("경고", "대상을 선택해 주세요.")
            return
        config = self.service.config
        idx = int(selected[0])
        config["sites"][idx]["enabled"] = not config["sites"][idx].get("enabled", True)
        self.service.config_manager.save_config(config)
        self._refresh_site_tree()

    def _delete_site(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("경고", "삭제할 대상을 선택해 주세요.")
            return
        if not messagebox.askyesno("확인", "선택한 사이트를 삭제하시겠습니까?"):
            return
        config = self.service.config
        config["sites"].pop(int(selected[0]))
        self.service.config_manager.save_config(config)
        self._refresh_site_tree()

    def _add_site_popup(self):
        self._open_site_dialog("사이트 등록", None)

    def _edit_site_popup(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("경고", "수정할 대상을 선택해 주세요.")
            return
        idx = int(selected[0])
        self._open_site_dialog("사이트 수정", idx, self.service.config["sites"][idx])

    def _open_site_dialog(self, title: str, idx: int = None, site_data: dict = None):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("560x540")
        dialog.resizable(False, False)
        dialog.configure(bg=self.BG_COLOR)
        dialog.grab_set()

        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(frame, text="사이트 이름:").grid(row=0, column=0, sticky="w", pady=8)
        name_entry = ttk.Entry(frame, width=40)
        name_entry.grid(row=0, column=1, sticky="w", pady=8)

        ttk.Label(frame, text="타입 (유형):").grid(row=1, column=0, sticky="w", pady=8)
        type_cb = ttk.Combobox(frame, values=["css", "rss", "naver", "tistory", "brunch", "youtube", "substack"], state="readonly", width=12)
        type_cb.grid(row=1, column=1, sticky="w", pady=8)
        type_cb.set("css")

        ttk.Label(frame, text="수집 주소(URL):").grid(row=2, column=0, sticky="w", pady=8)
        url_entry = ttk.Entry(frame, width=40)
        url_entry.grid(row=2, column=1, sticky="w", pady=8)

        css_frame = ttk.LabelFrame(frame, text=" CSS 선택자 설정 (CSS 타입 전용) ")
        css_frame.grid(row=3, column=0, columnspan=2, sticky="we", pady=10, ipady=5)

        ttk.Label(css_frame, text="아이템 컨테이너:").grid(row=0, column=0, sticky="w", padx=10, pady=5)
        item_entry = ttk.Entry(css_frame, width=28)
        item_entry.grid(row=0, column=1, sticky="w", pady=5)
        item_entry.insert(0, ".post-item")

        ttk.Label(css_frame, text="제목 선택자:").grid(row=1, column=0, sticky="w", padx=10, pady=5)
        title_entry = ttk.Entry(css_frame, width=28)
        title_entry.grid(row=1, column=1, sticky="w", pady=5)
        title_entry.insert(0, ".post-title")

        ttk.Label(css_frame, text="본문 선택자:").grid(row=2, column=0, sticky="w", padx=10, pady=5)
        content_entry = ttk.Entry(css_frame, width=28)
        content_entry.grid(row=2, column=1, sticky="w", pady=5)
        content_entry.insert(0, ".post-content")

        ttk.Label(frame, text="불필요 요소 제거 CSS:").grid(row=4, column=0, sticky="w", pady=8)
        remove_entry = ttk.Entry(frame, width=40)
        remove_entry.grid(row=4, column=1, sticky="w", pady=8)

        ttk.Label(frame, text="최대 수집 개수:").grid(row=5, column=0, sticky="w", pady=8)
        limit_entry = ttk.Entry(frame, width=10)
        limit_entry.grid(row=5, column=1, sticky="w", pady=8)
        limit_entry.insert(0, "5")

        # 이미지 포함 / 번역 옵션
        opt_frame = ttk.Frame(frame)
        opt_frame.grid(row=6, column=0, columnspan=2, sticky="we", pady=5)
        include_img_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="이미지 포함", variable=include_img_var).pack(side="left", padx=5)

        ttk.Label(opt_frame, text="번역:").pack(side="left", padx=(15, 3))
        translate_cb = ttk.Combobox(opt_frame, values=["", "ko", "en", "ja", "zh-cn", "zh-tw"], width=6)
        translate_cb.pack(side="left")
        translate_cb.set("")
        ttk.Label(opt_frame, text="(빈값=번역안함)", font=("Malgun Gothic", 8), foreground="#a6adc8").pack(side="left", padx=3)

        def on_type_change(event=None):
            t = type_cb.get()
            state = "disabled" if t in ("rss", "naver", "tistory", "brunch", "youtube", "substack") else "normal"
            for w in (item_entry, title_entry, content_entry, remove_entry):
                w.config(state=state)

        type_cb.bind("<<ComboboxSelected>>", on_type_change)

        if site_data:
            name_entry.insert(0, site_data.get("name", ""))
            type_cb.set(site_data.get("type", "css"))
            url_entry.insert(0, site_data.get("url", ""))
            item_entry.delete(0, tk.END); item_entry.insert(0, site_data.get("item_selector", ".post-item"))
            title_entry.delete(0, tk.END); title_entry.insert(0, site_data.get("title_selector", ".post-title"))
            content_entry.delete(0, tk.END); content_entry.insert(0, site_data.get("content_selector", ".post-content"))
            remove_entry.delete(0, tk.END); remove_entry.insert(0, site_data.get("remove_selectors", ""))
            limit_entry.delete(0, tk.END); limit_entry.insert(0, str(site_data.get("limit", 5)))
            include_img_var.set(site_data.get("include_images", False))
            translate_cb.set(site_data.get("translate_to", ""))
            on_type_change()

        def save_site():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            if not name or not url:
                messagebox.showerror("오류", "이름과 수집 주소는 필수값입니다.", parent=dialog)
                return
            try:
                limit = int(limit_entry.get().strip())
            except ValueError:
                messagebox.showerror("오류", "수집 개수는 숫자여야 합니다.", parent=dialog)
                return
            config = self.service.config
            new_site = {
                "name": name, "type": type_cb.get(), "url": url, "limit": limit,
                "enabled": site_data.get("enabled", True) if site_data else True,
                "include_images": include_img_var.get(),
                "translate_to": translate_cb.get().strip(),
            }
            if type_cb.get() == "css":
                new_site["item_selector"] = item_entry.get().strip()
                new_site["title_selector"] = title_entry.get().strip()
                new_site["content_selector"] = content_entry.get().strip()
                new_site["remove_selectors"] = remove_entry.get().strip()
            if idx is None:
                config["sites"].append(new_site)
            else:
                config["sites"][idx] = new_site
            self.service.config_manager.save_config(config)
            self._refresh_site_tree()
            dialog.destroy()

        dlg_btn_frame = ttk.Frame(dialog)
        dlg_btn_frame.pack(side="bottom", fill="x", pady=10)
        ttk.Button(dlg_btn_frame, text="저장", command=save_site).pack(side="right", padx=10)
        ttk.Button(dlg_btn_frame, text="취소", command=dialog.destroy).pack(side="right", padx=10)

    # ------------------------------------------------------------------
    # 동기화 이력 탭
    # ------------------------------------------------------------------
    def _refresh_history(self):
        for item in self.hist_tree.get_children():
            self.hist_tree.delete(item)
        rows = self.service.db.get_history(limit=200)
        for url, site_name, title, synced_at in rows:
            self.hist_tree.insert("", "end", iid=url, values=(
                site_name or "", title or "", synced_at or "", url or ""
            ))
        count = self.service.db.get_count()
        self.history_count_label.config(text=f"총 {count}건 기록됨")

    def _delete_history_entry(self):
        selected = self.hist_tree.selection()
        if not selected:
            messagebox.showwarning("경고", "삭제할 항목을 선택해 주세요.")
            return
        if not messagebox.askyesno("확인", f"{len(selected)}개 항목을 삭제하면 다음 동기화 시 재수집됩니다. 계속할까요?"):
            return
        for url in selected:
            self.service.db.delete_entry(url)
        self._refresh_history()
        self._log_message(f"🗑 이력 {len(selected)}건 삭제 완료 (재전송 허용)")

    def _clear_all_history(self):
        if not messagebox.askyesno("전체 초기화 확인", "모든 동기화 이력을 삭제합니다.\n다음 동기화 시 모든 기사가 재수집됩니다. 계속할까요?"):
            return
        self.service.db.clear_all()
        self._refresh_history()
        self._log_message("⚠️ 동기화 이력 전체 초기화 완료")

    # ------------------------------------------------------------------
    # OPDS / 웹 대시보드 / Calibre Watch 서버 제어
    # ------------------------------------------------------------------
    def _toggle_opds(self):
        if self._opds_server and self._opds_server.is_running:
            self._opds_server.stop()
            self._opds_server = None
            self.opds_start_btn.config(text="▶ 서버 시작")
            self.opds_status_label.config(text="중지됨", foreground=self.RED_COLOR)
            self.opds_url_label.config(text="")
        else:
            try:
                port = int(self.opds_port_sp.get())
            except ValueError:
                port = 8765
            output_dir = self.dir_entry.get().strip() or "./output"
            self._opds_server = OPDSServer(output_dir=output_dir, port=port)
            if self._opds_server.start():
                self.opds_start_btn.config(text="■ 서버 중지")
                self.opds_status_label.config(text="실행 중 ✅", foreground=self.GREEN_COLOR)
                url = self._opds_server.get_url()
                self.opds_url_label.config(text=url)
                self._log_message(f"📡 OPDS 서버 시작: {url}")
            else:
                messagebox.showerror("오류", f"OPDS 서버 시작 실패. 포트 {port}이 이미 사용 중일 수 있습니다.")

    def _toggle_web(self):
        if self._web_dashboard and self._web_dashboard.is_running:
            self._web_dashboard.stop()
            self._web_dashboard = None
            self.web_start_btn.config(text="▶ 서버 시작")
            self.web_status_label.config(text="중지됨", foreground=self.RED_COLOR)
            self.web_url_label.config(text="")
        else:
            try:
                port = int(self.web_port_sp.get())
            except ValueError:
                port = 8766

            def sync_cb():
                self.service.run_sync_pipeline(
                    log_callback=lambda msg: self.root.after(0, lambda: self._log_message(msg))
                )

            self._web_dashboard = WebDashboard(port=port, sync_callback=sync_cb)
            if self._web_dashboard.start():
                self.web_start_btn.config(text="■ 서버 중지")
                self.web_status_label.config(text="실행 중 ✅", foreground=self.GREEN_COLOR)
                url = self._web_dashboard.get_url()
                self.web_url_label.config(text=url)
                self._log_message(f"🌐 웹 대시보드 시작: {url}")
            else:
                messagebox.showerror("오류", f"웹 대시보드 시작 실패. 포트 {port}이 이미 사용 중일 수 있습니다.")

    def _toggle_watch(self):
        if self._calibre_watcher and self._calibre_watcher.is_running:
            self._calibre_watcher.stop()
            self._calibre_watcher = None
            self.watch_start_btn.config(text="▶ 감시 시작")
            self.watch_status_label.config(text="감시 중지됨", foreground=self.RED_COLOR)
        else:
            watch_dir = self.watch_dir_entry.get().strip()
            if not watch_dir or not os.path.isdir(watch_dir):
                messagebox.showerror("오류", "유효한 감시 폴더를 선택해 주세요.")
                return
            ip = self.ip_entry.get().strip()

            def on_new_file(fpath: str):
                self._log_message(f"👁 새 파일 감지: {os.path.basename(fpath)} → 자동 전송 시작")
                def upload_task():
                    ok = X3Uploader(ip).upload(fpath)
                    msg = f"🎉 자동 전송 성공: {os.path.basename(fpath)}" if ok else f"❌ 자동 전송 실패: {os.path.basename(fpath)}"
                    self.root.after(0, lambda: self._log_message(msg))
                threading.Thread(target=upload_task, daemon=True).start()

            self._calibre_watcher = CalibreWatcher(watch_dir, on_new_file)
            if self._calibre_watcher.start():
                self.watch_start_btn.config(text="■ 감시 중지")
                self.watch_status_label.config(text=f"✅ 감시 중: {watch_dir}", foreground=self.GREEN_COLOR)
                self._log_message(f"👁 Calibre Watch 시작: {watch_dir}")
                # 설정 저장
                config = self.service.config
                config["calibre_watch"] = {"enabled": True, "watch_dir": watch_dir}
                self.service.config_manager.save_config(config)
            else:
                messagebox.showerror("오류", "파일 감시 시작 실패. watchdog 패키지가 설치되어 있는지 확인하세요.")

    # ------------------------------------------------------------------
    # 동기화 실행
    # ------------------------------------------------------------------
    def _run_immediate_sync(self):
        self._save_ui_settings()
        self.sync_now_btn.config(state="disabled")
        self.progress_bar["value"] = 0
        self._log_message("\n=== 동기화 실행 요청 받음 ===")

        def run():
            self.service.run_sync_pipeline(
                log_callback=lambda msg: self.root.after(0, lambda: self._log_message(msg)),
                progress_callback=lambda cur, tot: self.root.after(0, lambda: self._update_progress(cur, tot))
            )
            self.root.after(0, self._sync_finished_ui)

        threading.Thread(target=run, daemon=True).start()

    def _sync_finished_ui(self):
        self.sync_now_btn.config(state="normal")
        self.progress_bar["value"] = 0
        self._log_message("=== 동기화 프로세스 종료 ===\n")
        self._refresh_history()

    # ------------------------------------------------------------------
    # 종료 처리
    # ------------------------------------------------------------------
    def _on_close(self):
        if self._opds_server:
            self._opds_server.stop()
        if self._web_dashboard:
            self._web_dashboard.stop()
        if self._calibre_watcher:
            self._calibre_watcher.stop()
        self.root.destroy()

    def run(self):
        self.root.mainloop()
