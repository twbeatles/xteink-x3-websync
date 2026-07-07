import os
import hashlib
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.integrations.calibre import CalibreManager
from websync.core.paths import resolve_path
from websync.upload.uploader import X3Uploader
from websync.scheduler.manager import SchedulerManager
from websync.integrations.notifier import ToastNotifier
from websync.pipeline.service import SyncService
from websync.servers.opds import OPDSServer
from websync.watch.calibre import CalibreWatcher
from websync.servers.web_dashboard import WebDashboard
from websync.core.logger import get_log_dir

class SyncAppGui:
    """Tkinter를 기반으로 탭형 인터페이스를 제공하고 비즈니스 흐름을 연동하는 클래스"""
    def __init__(self, service: SyncService):
        self.service = service
        self.scheduler = SchedulerManager()
        self.calibre = CalibreManager(
            self.service.config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"),
            self.service.config.get("calibre_library_path", ""),
        )

        # 서버 인스턴스
        self._opds_server: OPDSServer | None = None
        self._web_dashboard: WebDashboard | None = None
        self._calibre_watcher: CalibreWatcher | None = None
        self._history_url_by_iid: dict[str, str] = {}

        self.root = tk.Tk()
        self.root.title("Xteink X3 WebSync Manager")
        self.root.geometry("860x760")
        self.root.minsize(640, 480)
        self.root.resizable(True, True)

        self._sync_busy = False

        self._setup_styles()
        self._build_ui()
        self._load_config_to_ui()
        self.root.after(0, lambda: self._center_window(self.root, 860, 760))

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
        self.HINT_COLOR    = "#6c757d" # 보조 힌트 텍스트

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
        self.style.configure("TCheckbutton", background=self.BG_COLOR, foreground=self.FG_COLOR)

    # ------------------------------------------------------------------
    # UI 헬퍼
    # ------------------------------------------------------------------
    def _center_window(self, window: tk.Misc, width: int | None = None, height: int | None = None) -> None:
        window.update_idletasks()
        w = width or window.winfo_width()
        h = height or window.winfo_height()
        x = max(0, (window.winfo_screenwidth() - w) // 2)
        y = max(0, (window.winfo_screenheight() - h) // 2)
        if width and height:
            window.geometry(f"{width}x{height}+{x}+{y}")
        else:
            window.geometry(f"+{x}+{y}")

    def _setup_dialog(self, dialog: tk.Toplevel, width: int, height: int, *, resizable: bool = True) -> None:
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(resizable, resizable)
        dialog.minsize(min(width, 420), min(height, 240))
        self._center_window(dialog, width, height)

    def _bind_widget_mousewheel(self, widget: tk.Misc, handler) -> None:
        widget.bind("<MouseWheel>", handler, add="+")
        for child in widget.winfo_children():
            if child.winfo_class() in ("Treeview", "Text", "TCombobox", "TSpinbox"):
                continue
            self._bind_widget_mousewheel(child, handler)

    def _bind_text_mousewheel(self, text_widget: tk.Text) -> None:
        def _on_mousewheel(event):
            text_widget.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"
        text_widget.bind("<MouseWheel>", _on_mousewheel)

    def _create_scrolled_tree(
        self,
        parent,
        columns,
        show: str = "headings",
        height: int = 10,
        *,
        padx: int = 10,
        pady: int = 8,
        **tree_kwargs,
    ) -> ttk.Treeview:
        """스크롤바가 붙은 Treeview를 생성합니다. (pack/grid 혼용 방지)"""
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="both", expand=True, padx=padx, pady=pady)
        wrapper.grid_rowconfigure(0, weight=1)
        wrapper.grid_columnconfigure(0, weight=1)

        tree = ttk.Treeview(wrapper, columns=columns, show=show, height=height, **tree_kwargs)
        vsb = ttk.Scrollbar(wrapper, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(wrapper, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        return tree

    def _set_sync_ui_busy(self, busy: bool) -> None:
        self._sync_busy = busy
        state = "disabled" if busy else "normal"
        for widget in (
            self.sync_now_btn,
            self.direct_upload_btn,
            self.calibre_send_btn,
            self.calibre_conn_btn,
            self.test_conn_btn,
        ):
            widget.config(state=state)

    def _bind_autosave(self, widget: tk.Misc) -> None:
        widget.bind("<FocusOut>", lambda _e: self._save_ui_settings())

    # ------------------------------------------------------------------
    # 스크롤 컨테이너
    # ------------------------------------------------------------------
    def _create_scrollable_frame(self, parent) -> ttk.Frame:
        """세로 스크롤이 가능한 내부 프레임을 생성합니다."""
        container = ttk.Frame(parent)
        container.pack(fill="both", expand=True)

        canvas = tk.Canvas(container, highlightthickness=0, bg=self.BG_COLOR)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        def _on_frame_configure(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        scrollable_frame.bind("<Configure>", _on_frame_configure)

        window_id = canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")

        def _on_canvas_configure(event):
            canvas.itemconfig(window_id, width=event.width)

        canvas.bind("<Configure>", _on_canvas_configure)
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            return "break"

        self._bind_widget_mousewheel(scrollable_frame, _on_mousewheel)
        canvas.bind("<MouseWheel>", _on_mousewheel)

        return scrollable_frame

    # ------------------------------------------------------------------
    # UI 빌드
    # ------------------------------------------------------------------
    def _build_ui(self):
        self.main_paned = ttk.PanedWindow(self.root, orient=tk.VERTICAL)
        self.main_paned.pack(fill="both", expand=True, padx=10, pady=10)

        tab_container = ttk.Frame(self.main_paned)
        self.main_paned.add(tab_container, weight=3)

        self.notebook = ttk.Notebook(tab_container)
        self.notebook.pack(fill="both", expand=True)

        self.tab_sync    = ttk.Frame(self.notebook)
        self.tab_calibre = ttk.Frame(self.notebook)
        self.tab_history = ttk.Frame(self.notebook)
        self.tab_server  = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_sync,    text=" 뉴스 동기화 ")
        self.notebook.add(self.tab_calibre, text=" Calibre 서재 ")
        self.notebook.add(self.tab_history, text=" 📋 동기화 이력 ")
        self.notebook.add(self.tab_server,  text=" ⚙️ 서버 설정 ")

        self._build_tab_sync()
        self._build_tab_calibre()
        self._build_tab_history()
        self._build_tab_server()

        bottom_container = ttk.Frame(self.main_paned)
        self.main_paned.add(bottom_container, weight=1)
        self._build_bottom_bar(bottom_container)

    # ── 탭 1: 뉴스 동기화 ────────────────────────────────────────────
    def _build_tab_sync(self):
        body = self._create_scrollable_frame(self.tab_sync)

        # 기기 및 경로
        settings_frame = ttk.LabelFrame(body, text=" 기기 및 경로 설정 ")
        settings_frame.pack(fill="x", padx=15, pady=8)
        settings_frame.columnconfigure(1, weight=1)

        ttk.Label(settings_frame, text="X3 주소 (IP/호스트):").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.ip_entry = ttk.Entry(settings_frame, width=22, font=("Consolas", 10))
        self.ip_entry.grid(row=0, column=1, padx=5, pady=6, sticky="we")
        self.test_conn_btn = ttk.Button(settings_frame, text="연결 확인", command=self._test_connection)
        self.test_conn_btn.grid(row=0, column=2, padx=5, pady=6)
        self.conn_status_label = ttk.Label(settings_frame, text="미확인", foreground=self.YELLOW_COLOR)
        self.conn_status_label.grid(row=0, column=3, padx=10, pady=6, sticky="w")

        ttk.Label(settings_frame, text="출력 저장 폴더:").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.dir_entry = ttk.Entry(settings_frame)
        self.dir_entry.grid(row=1, column=1, padx=5, pady=6, sticky="we")
        ttk.Button(settings_frame, text="폴더 선택", command=self._browse_directory).grid(row=1, column=2, padx=5, pady=6)
        ttk.Button(settings_frame, text="📂 열기", command=self._open_output_folder).grid(row=1, column=3, padx=5, pady=6)

        self._bind_autosave(self.ip_entry)
        self._bind_autosave(self.dir_entry)

        devices_frame = ttk.LabelFrame(body, text=" 추가 X3 기기 (다중 무선 전송) ")
        devices_frame.pack(fill="x", padx=15, pady=5)
        devices_frame.columnconfigure(0, weight=1)

        devices_inner = ttk.Frame(devices_frame)
        devices_inner.pack(fill="x", padx=10, pady=8)
        devices_inner.columnconfigure(0, weight=1)
        devices_inner.rowconfigure(0, weight=1)

        tree_holder = ttk.Frame(devices_inner)
        tree_holder.grid(row=0, column=0, sticky="nsew")
        self.devices_tree = self._create_scrolled_tree(
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
            foreground=self.HINT_COLOR,
        ).pack(fill="x", padx=10, pady=(0, 6))

        # 폰트 설정
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
        self.font_cb.bind("<<ComboboxSelected>>", lambda _e: self._save_ui_settings())

        ttk.Label(font_frame, text="글자 크기:").grid(row=0, column=2, padx=15, pady=6, sticky="w")
        self.font_size_sp = ttk.Spinbox(font_frame, from_=10, to=30, width=5)
        self.font_size_sp.grid(row=0, column=3, padx=5, pady=6, sticky="w")
        self.font_size_sp.set("16")
        self._bind_autosave(self.font_size_sp)

        ttk.Label(font_frame, text="줄 간격:").grid(row=0, column=4, padx=15, pady=6, sticky="w")
        self.line_height_sp = ttk.Spinbox(font_frame, from_=1.0, to=3.0, increment=0.1, width=5)
        self.line_height_sp.grid(row=0, column=5, padx=5, pady=6, sticky="w")
        self.line_height_sp.set("1.7")
        self._bind_autosave(self.line_height_sp)

        self.cover_var = tk.BooleanVar(value=True)
        cover_cb = ttk.Checkbutton(font_frame, text="EPUB 표지 자동 생성", variable=self.cover_var, command=self._save_ui_settings)
        cover_cb.grid(row=1, column=0, columnspan=2, padx=10, pady=(0, 6), sticky="w")

        # 사이트 관리
        sites_frame = ttk.LabelFrame(body, text=" 동기화 대상 사이트 관리 ")
        sites_frame.pack(fill="x", padx=15, pady=5)

        columns = ("name", "type", "enabled", "url")
        self.tree = self._create_scrolled_tree(sites_frame, columns, height=6)
        self.tree.heading("name", text="사이트 이름")
        self.tree.heading("type", text="유형")
        self.tree.heading("enabled", text="활성화")
        self.tree.heading("url", text="URL")
        self.tree.column("name", width=140, minwidth=80, anchor="w")
        self.tree.column("type", width=60, minwidth=50, anchor="center")
        self.tree.column("enabled", width=55, minwidth=45, anchor="center")
        self.tree.column("url", width=390, minwidth=120, anchor="w")
        self.tree.bind("<Double-1>", lambda _e: self._edit_site_popup())

        btn_frame = ttk.Frame(sites_frame)
        btn_frame.pack(fill="x", padx=10, pady=(0, 8))
        ttk.Button(btn_frame, text="사이트 추가", command=self._add_site_popup).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="사이트 수정", command=self._edit_site_popup).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="선택 삭제", command=self._delete_site).pack(side="left", padx=3)
        ttk.Button(btn_frame, text="활성 토글", command=self._toggle_site_enabled).pack(side="left", padx=3)

        # 하단 그리드: 직접 전송 + 스케줄러
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
        self.sched_status_label = ttk.Label(scheduler_frame, text="스케줄 확인 중...", font=("Malgun Gothic", 8), foreground=self.HINT_COLOR)
        self.sched_status_label.grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 6), sticky="w")

    # ── 탭 2: Calibre 서재 ──────────────────────────────────────────
    def _build_tab_calibre(self):
        body = self._create_scrollable_frame(self.tab_calibre)

        calibre_top_frame = ttk.LabelFrame(body, text=" Calibre 연동 설정 ")
        calibre_top_frame.pack(fill="x", padx=15, pady=10)
        calibre_top_frame.columnconfigure(1, weight=1)

        ttk.Label(calibre_top_frame, text="calibredb.exe 경로:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.calibre_entry = ttk.Entry(calibre_top_frame)
        self.calibre_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(calibre_top_frame, text="찾아보기", command=self._browse_calibredb).grid(row=0, column=2, padx=5, pady=8)
        self.calibre_conn_btn = ttk.Button(calibre_top_frame, text="연결 확인 & 서재 로드", command=self._test_and_load_calibre)
        self.calibre_conn_btn.grid(row=0, column=3, padx=10, pady=8)
        self._bind_autosave(self.calibre_entry)

        ttk.Label(calibre_top_frame, text="라이브러리 경로 (선택):").grid(row=1, column=0, padx=10, pady=8, sticky="w")
        self.calibre_lib_entry = ttk.Entry(calibre_top_frame)
        self.calibre_lib_entry.grid(row=1, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(calibre_top_frame, text="폴더 선택", command=self._browse_calibre_library).grid(row=1, column=2, padx=5, pady=8)
        ttk.Label(
            calibre_top_frame,
            text="비워두면 Calibre 기본 라이브러리 사용",
            font=("Malgun Gothic", 8),
            foreground=self.HINT_COLOR,
        ).grid(row=1, column=3, padx=10, pady=8, sticky="w")
        self._bind_autosave(self.calibre_lib_entry)

        calibre_list_frame = ttk.LabelFrame(body, text=" 내 Calibre 서재 도서 목록 ")
        calibre_list_frame.pack(fill="x", padx=15, pady=5)

        c_columns = ("id", "title", "authors", "formats")
        self.calibre_tree = self._create_scrolled_tree(
            calibre_list_frame, c_columns, height=8, padx=10, pady=10
        )
        self.calibre_tree.heading("id", text="ID")
        self.calibre_tree.heading("title", text="도서 제목")
        self.calibre_tree.heading("authors", text="저자")
        self.calibre_tree.heading("formats", text="보유 포맷")
        self.calibre_tree.column("id", width=50, minwidth=40, anchor="center")
        self.calibre_tree.column("title", width=320, minwidth=120, anchor="w")
        self.calibre_tree.column("authors", width=180, minwidth=80, anchor="w")
        self.calibre_tree.column("formats", width=120, minwidth=80, anchor="center")

        calibre_action_frame = ttk.Frame(body)
        calibre_action_frame.pack(fill="x", padx=15, pady=10)
        self.calibre_send_btn = ttk.Button(calibre_action_frame, text="★ 선택한 도서 X3 기기로 즉시 전송 (다중 선택 가능)", command=self._send_calibre_books)
        self.calibre_send_btn.pack(fill="x", pady=5)

    # ── 탭 3: 동기화 이력 ───────────────────────────────────────────
    def _build_tab_history(self):
        body = self._create_scrollable_frame(self.tab_history)

        ctrl_frame = ttk.Frame(body)
        ctrl_frame.pack(fill="x", padx=15, pady=8)

        btn_row = ttk.Frame(ctrl_frame)
        btn_row.pack(fill="x")
        ttk.Button(btn_row, text="🔄 이력 새로고침", command=self._refresh_history).pack(side="left", padx=3)
        ttk.Button(btn_row, text="🗑 선택 항목 삭제 (재전송 허용)", command=self._delete_history_entry).pack(side="left", padx=3)
        ttk.Button(btn_row, text="⚠️ 전체 이력 초기화", command=self._clear_all_history).pack(side="left", padx=3)

        self.history_count_label = ttk.Label(ctrl_frame, text="", foreground=self.YELLOW_COLOR)
        self.history_count_label.pack(anchor="e", padx=10, pady=(4, 0))

        hist_frame = ttk.LabelFrame(body, text=" 전송 완료된 포스트 목록 (최신 200건) ")
        hist_frame.pack(fill="x", padx=15, pady=5)

        h_columns = ("site", "title", "synced_at", "url")
        self.hist_tree = self._create_scrolled_tree(
            hist_frame, h_columns, height=10, selectmode="extended"
        )
        self.hist_tree.heading("site", text="사이트")
        self.hist_tree.heading("title", text="제목")
        self.hist_tree.heading("synced_at", text="전송 시각")
        self.hist_tree.heading("url", text="URL")
        self.hist_tree.column("site", width=120, minwidth=80, anchor="w")
        self.hist_tree.column("title", width=280, minwidth=120, anchor="w")
        self.hist_tree.column("synced_at", width=150, minwidth=100, anchor="center")
        self.hist_tree.column("url", width=250, minwidth=120, anchor="w")
        self.hist_tree.bind("<Double-1>", self._on_history_double_click)

    # ── 탭 4: 서버 & 고급 설정 ────────────────────────────────────
    def _build_tab_server(self):
        body = self._create_scrollable_frame(self.tab_server)

        # OPDS 서버
        opds_frame = ttk.LabelFrame(body, text=" 📡 OPDS 카탈로그 서버 ")
        opds_frame.pack(fill="x", padx=15, pady=10)
        opds_frame.columnconfigure(4, weight=1)
        ttk.Label(opds_frame, text="포트:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.opds_port_sp = ttk.Spinbox(opds_frame, from_=1024, to=65535, width=6)
        self.opds_port_sp.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.opds_port_sp.set("8765")
        self.opds_start_btn = ttk.Button(opds_frame, text="▶ 서버 시작", command=self._toggle_opds)
        self.opds_start_btn.grid(row=0, column=2, padx=5, pady=8)
        self.opds_status_label = ttk.Label(opds_frame, text="중지됨", foreground=self.RED_COLOR)
        self.opds_status_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.opds_url_label = ttk.Label(opds_frame, text="", foreground=self.ACCENT_COLOR, cursor="hand2")
        self.opds_url_label.grid(row=1, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.opds_url_label.bind("<Button-1>", lambda e: self._open_url(self.opds_url_label.cget("text")))
        self.opds_allow_lan_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opds_frame, text="LAN 공개 (0.0.0.0)", variable=self.opds_allow_lan_var, command=self._save_ui_settings).grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="w")
        ttk.Label(opds_frame, text="기본은 localhost만 허용. LAN 공개 시 API 키 인증 필요.", font=("Malgun Gothic", 8), foreground=self.HINT_COLOR).grid(row=3, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.opds_api_key_label = ttk.Label(opds_frame, text="", font=("Consolas", 8), foreground=self.HINT_COLOR)
        self.opds_api_key_label.grid(row=4, column=0, columnspan=5, padx=10, pady=(0, 8), sticky="w")
        self._bind_autosave(self.opds_port_sp)

        # 웹 대시보드
        web_frame = ttk.LabelFrame(body, text=" 🌐 웹 대시보드 ")
        web_frame.pack(fill="x", padx=15, pady=5)
        web_frame.columnconfigure(4, weight=1)
        ttk.Label(web_frame, text="포트:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.web_port_sp = ttk.Spinbox(web_frame, from_=1024, to=65535, width=6)
        self.web_port_sp.grid(row=0, column=1, padx=5, pady=8, sticky="w")
        self.web_port_sp.set("8766")
        self.web_start_btn = ttk.Button(web_frame, text="▶ 서버 시작", command=self._toggle_web)
        self.web_start_btn.grid(row=0, column=2, padx=5, pady=8)
        self.web_status_label = ttk.Label(web_frame, text="중지됨", foreground=self.RED_COLOR)
        self.web_status_label.grid(row=0, column=3, padx=10, pady=8, sticky="w")
        self.web_url_label = ttk.Label(web_frame, text="", foreground=self.ACCENT_COLOR, cursor="hand2")
        self.web_url_label.grid(row=1, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.web_url_label.bind("<Button-1>", lambda e: self._open_url(self.web_url_label.cget("text")))
        self.web_allow_lan_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(web_frame, text="LAN 공개 (0.0.0.0)", variable=self.web_allow_lan_var, command=self._save_ui_settings).grid(row=2, column=0, columnspan=2, padx=10, pady=(0, 4), sticky="w")
        ttk.Label(
            web_frame,
            text="⚠️ LAN 공개 시 HTTP 평문 전송 — 신뢰할 수 있는 네트워크에서만 사용하세요.",
            font=("Malgun Gothic", 8),
            foreground=self.RED_COLOR,
        ).grid(row=3, column=0, columnspan=5, padx=10, pady=(0, 4), sticky="w")
        self.web_token_label = ttk.Label(web_frame, text="", font=("Consolas", 8), foreground=self.HINT_COLOR)
        self.web_token_label.grid(row=4, column=0, columnspan=5, padx=10, pady=(0, 8), sticky="w")
        self._bind_autosave(self.web_port_sp)

        # Calibre Watch
        watch_frame = ttk.LabelFrame(body, text=" 👁 Calibre 서재 자동 감시 (새 파일 추가 시 자동 전송) ")
        watch_frame.pack(fill="x", padx=15, pady=5)
        watch_frame.columnconfigure(1, weight=1)
        ttk.Label(watch_frame, text="감시 폴더:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.watch_dir_entry = ttk.Entry(watch_frame)
        self.watch_dir_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        ttk.Button(watch_frame, text="폴더 선택", command=self._browse_watch_dir).grid(row=0, column=2, padx=5, pady=8)
        self.watch_start_btn = ttk.Button(watch_frame, text="▶ 감시 시작", command=self._toggle_watch)
        self.watch_start_btn.grid(row=0, column=3, padx=5, pady=8)
        self.watch_status_label = ttk.Label(watch_frame, text="감시 중지됨", foreground=self.RED_COLOR)
        self.watch_status_label.grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 8), sticky="w")
        self._bind_autosave(self.watch_dir_entry)

        # AI 요약 설정
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

        # 번역 설정
        trans_frame = ttk.LabelFrame(body, text=" 🌐 번역 설정 (선택) ")
        trans_frame.pack(fill="x", padx=15, pady=5)

        self.trans_enabled_var = tk.BooleanVar()
        ttk.Checkbutton(trans_frame, text="번역 활성화", variable=self.trans_enabled_var).grid(row=0, column=0, padx=10, pady=6, sticky="w")

        ttk.Label(trans_frame, text="프로바이더:").grid(row=0, column=1, padx=10, pady=6, sticky="w")
        self.trans_provider_cb = ttk.Combobox(trans_frame, values=["googletrans", "libretranslate"], width=14, state="readonly")
        self.trans_provider_cb.grid(row=0, column=2, padx=5, pady=6)
        self.trans_provider_cb.set("googletrans")

        ttk.Button(trans_frame, text="저장", command=self._save_trans_settings).grid(row=0, column=3, padx=10, pady=6)
        ttk.Label(trans_frame, text="※ googletrans: 사이트별 '번역'만 설정해도 동작. libretranslate: 전역 활성화 필요.", font=("Malgun Gothic", 8), foreground=self.HINT_COLOR).grid(row=1, column=0, columnspan=4, padx=10, pady=(0, 6), sticky="w")

        # 로그 폴더 열기
        log_frame = ttk.LabelFrame(body, text=" 📂 로그 파일 ")
        log_frame.pack(fill="x", padx=15, pady=5)
        ttk.Button(log_frame, text="📂 로그 폴더 열기", command=self._open_log_folder).pack(side="left", padx=10, pady=8)
        ttk.Label(log_frame, text="logs/ 폴더에 날짜별 sync_YYYY-MM-DD.log 파일이 저장됩니다.", font=("Malgun Gothic", 8), foreground=self.HINT_COLOR).pack(side="left", padx=5, pady=8)

    # ── 하단 공통 바 ──────────────────────────────────────────────
    def _build_bottom_bar(self, parent):
        sync_run_frame = ttk.Frame(parent)
        sync_run_frame.pack(fill="x", padx=5, pady=2)

        self.sync_now_btn = ttk.Button(sync_run_frame, text="🚀 즉시 전체 뉴스 스크래핑 및 X3 동기화 실행", command=self._run_immediate_sync)
        self.sync_now_btn.pack(fill="x", pady=3)

        # 진행률 표시바
        self.progress_bar = ttk.Progressbar(parent, orient="horizontal", mode="determinate", style="TProgressbar")
        self.progress_bar.pack(fill="x", padx=5, pady=(0, 2))

        log_frame = ttk.LabelFrame(parent, text=" 프로그램 상태 및 동기화 로그 ")
        log_frame.pack(fill="both", expand=True, padx=5, pady=(2, 5))

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill="both", expand=True, padx=8, pady=8)

        self.log_txt = tk.Text(log_inner, height=6, bg=self.TEXT_BG, fg=self.FG_COLOR, insertbackground=self.FG_COLOR, font=("Consolas", 9), wrap="word")
        self.log_txt.pack(side="left", fill="both", expand=True)

        log_scroll = ttk.Scrollbar(log_inner, orient="vertical", command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log_txt.config(state="disabled")
        self._bind_text_mousewheel(self.log_txt)

    # ------------------------------------------------------------------
    # 내부 유틸
    # ------------------------------------------------------------------
    def _on_history_double_click(self, _event=None):
        selected = self.hist_tree.selection()
        if not selected:
            return
        url = self._history_url_by_iid.get(selected[0], "")
        if not url:
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(url)
        self._log_message(f"📋 URL 복사됨: {url[:80]}{'...' if len(url) > 80 else ''}")
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

    def _make_log_callback(self):
        return lambda msg: self.root.after(0, lambda m=msg: self._log_message(m))

    def _make_progress_callback(self):
        return lambda cur, tot: self.root.after(0, lambda c=cur, t=tot: self._update_progress(c, t))

    def _make_uploader(self) -> X3Uploader:
        """기본 기기 + x3_devices 전체에 전송할 업로더를 생성합니다."""
        config = self.service.config
        return X3Uploader(
            config.get("x3_ip", "").strip() or self.ip_entry.get().strip(),
            config.get("x3_devices", []),
        )

    @staticmethod
    def _summarize_upload_results(results: dict) -> tuple[bool, bool, str]:
        """(전체 성공, 일부 성공, 로그용 요약 문자열) 반환"""
        if not results:
            return False, False, "등록된 기기 없음"
        ok_names = [n for n, ok in results.items() if ok]
        fail_names = [n for n, ok in results.items() if not ok]
        parts = []
        if ok_names:
            parts.append(f"성공: {', '.join(ok_names)}")
        if fail_names:
            parts.append(f"실패: {', '.join(fail_names)}")
        return all(results.values()), bool(ok_names), " | ".join(parts)

    def _get_log_for_web(self) -> str:
        try:
            content = self.log_txt.get("1.0", "end-1c")
            if content.strip():
                lines = content.splitlines()
                return "\n".join(lines[-100:])
        except Exception:
            pass
        log_dir = get_log_dir()
        if os.path.isdir(log_dir):
            files = sorted(os.listdir(log_dir), reverse=True)
            if files:
                try:
                    with open(os.path.join(log_dir, files[0]), "r", encoding="utf-8") as f:
                        return "".join(f.readlines()[-100:])
                except Exception:
                    pass
        return ""

    # ------------------------------------------------------------------
    # 설정 로드 / 저장
    # ------------------------------------------------------------------
    def _load_config_to_ui(self):
        config = self.service.config
        self.ip_entry.insert(0, config.get("x3_ip", "crosspoint.local"))
        self.dir_entry.insert(0, config.get("output_dir", "./output"))
        self.calibre_entry.insert(0, config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"))
        self.calibre_lib_entry.insert(0, config.get("calibre_library_path", ""))
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
        self.opds_allow_lan_var.set(opds_conf.get("allow_lan", False))
        opds_key = opds_conf.get("api_key", "")
        self.opds_api_key_label.config(
            text=f"OPDS API 키: {opds_key[:8]}... (config.json, LAN 시 X-Api-Key 헤더)" if opds_key else ""
        )

        web_conf = config.get("web_dashboard", {})
        self.web_port_sp.set(str(web_conf.get("port", 8766)))
        self.web_allow_lan_var.set(web_conf.get("allow_lan", False))
        token = web_conf.get("api_token", "")
        self.web_token_label.config(text=f"API 토큰: {token[:8]}... (config.json)" if token else "")

        self._refresh_devices_tree()

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
        config["calibre_library_path"] = self.calibre_lib_entry.get().strip()
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
        try:
            config.setdefault("opds_server", {})["port"] = int(self.opds_port_sp.get())
            config["opds_server"]["allow_lan"] = self.opds_allow_lan_var.get()
        except ValueError:
            pass
        try:
            config.setdefault("web_dashboard", {})["port"] = int(self.web_port_sp.get())
            config["web_dashboard"]["allow_lan"] = self.web_allow_lan_var.get()
        except ValueError:
            pass
        config.setdefault("calibre_watch", {})["watch_dir"] = self.watch_dir_entry.get().strip()
        self.service.config_manager.save_config(config)
        self.calibre.calibre_path = config["calibre_path"]
        self.calibre.library_path = config["calibre_library_path"]
        self.service._reload_config()

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

    def _browse_calibre_library(self):
        d = filedialog.askdirectory(title="Calibre 라이브러리 폴더 선택 (metadata.db가 있는 폴더)")
        if d:
            self.calibre_lib_entry.delete(0, tk.END)
            self.calibre_lib_entry.insert(0, d)
            self._save_ui_settings()

    def _browse_watch_dir(self):
        d = filedialog.askdirectory(title="감시할 Calibre 라이브러리 폴더 선택")
        if d:
            self.watch_dir_entry.delete(0, tk.END)
            self.watch_dir_entry.insert(0, d)
            self._save_ui_settings()

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
        self.conn_status_label.config(text="연결 중...", foreground=self.YELLOW_COLOR)
        self.test_conn_btn.config(state="disabled")

        def task():
            uploader = self._make_uploader()
            results = []
            for dev in uploader._build_target_list():
                ok = uploader.test_connection(dev["ip"])
                results.append((dev["name"], dev["ip"], ok))
            self.root.after(0, lambda: self._test_connection_finished(results))

        threading.Thread(target=task, daemon=True).start()

    def _test_connection_finished(self, results: list[tuple[str, str, bool]]):
        if not self._sync_busy:
            self.test_conn_btn.config(state="normal")
        if not results:
            self.conn_status_label.config(text="등록된 기기 없음", foreground=self.RED_COLOR)
            return
        ok_count = sum(1 for _, _, ok in results if ok)
        if ok_count == len(results):
            self.conn_status_label.config(text=f"전체 {len(results)}대 연결 성공 ✅", foreground=self.GREEN_COLOR)
        elif ok_count > 0:
            failed = [name for name, _, ok in results if not ok]
            self.conn_status_label.config(
                text=f"부분 성공 ({ok_count}/{len(results)}) — 실패: {', '.join(failed)}",
                foreground=self.YELLOW_COLOR,
            )
        else:
            self.conn_status_label.config(text="모든 기기 연결 실패 ❌", foreground=self.RED_COLOR)
        for name, ip, ok in results:
            status = "✅" if ok else "❌"
            self._log_message(f"   {status} [{name}] {ip}")

    def _direct_upload(self):
        file_path = self.file_entry.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("경고", "올바른 파일 경로를 지정해 주세요.")
            return
        self._save_ui_settings()
        self._log_message(f"📡 로컬 파일 직접 전송 중: {os.path.basename(file_path)}")
        self.direct_upload_btn.config(state="disabled")

        def task():
            results = self._make_uploader().upload_to_targets(file_path)
            self.root.after(0, lambda: self._direct_upload_finished(results, file_path))

        threading.Thread(target=task, daemon=True).start()

    def _direct_upload_finished(self, results: dict, file_path: str):
        if not self._sync_busy:
            self.direct_upload_btn.config(state="normal")
        all_ok, any_ok, summary = self._summarize_upload_results(results)
        basename = os.path.basename(file_path)
        if all_ok:
            self._log_message(f"🎉 파일 전송 성공 ({basename}): {summary}")
            ToastNotifier.show_toast("파일 업로드 성공", f"'{basename}' 전송 완료.")
            messagebox.showinfo("완료", f"모든 기기로 전송 완료.\n{summary}")
        elif any_ok:
            self._log_message(f"⚠️ 파일 부분 전송 ({basename}): {summary}")
            ToastNotifier.show_toast("파일 부분 업로드", summary, is_error=True)
            messagebox.showwarning("부분 성공", f"일부 기기만 전송되었습니다.\n{summary}")
        else:
            self._log_message(f"❌ 파일 전송 실패 ({basename}): {summary}")
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
        self.calibre.library_path = self.calibre_lib_entry.get().strip()
        if not silent:
            self._log_message("📚 Calibre 연결 확인 중...")
            self.calibre_conn_btn.config(state="disabled")
        if not self.calibre.test_connection():
            if not silent:
                self._log_message("❌ Calibre 연동 실패: 경로를 확인하세요.")
                messagebox.showerror("Calibre 연동 실패", "calibredb.exe 경로를 찾지 못했습니다.")
                if not self._sync_busy:
                    self.calibre_conn_btn.config(state="normal")
            return
        threading.Thread(target=lambda: self.root.after(0, lambda: self._show_calibre_books(self.calibre.list_books(), silent)), daemon=True).start()

    def _show_calibre_books(self, books: list, silent: bool):
        if not self._sync_busy:
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
        self.calibre_send_btn.config(state="disabled")
        self._log_message(f"\n=== Calibre 책 {len(selected_items)}권 무선 전송 시작 ===")

        def task():
            success_cnt = 0
            uploader = self._make_uploader()
            for item_id in selected_items:
                book_id = int(item_id)
                file_path = self.calibre.get_book_file_path(book_id)
                if not file_path or not os.path.exists(file_path):
                    self.root.after(0, lambda b=book_id: self._log_message(f"❌ [책 ID {b}] 파일 경로 조회 실패"))
                    continue
                self.root.after(0, lambda p=file_path: self._log_message(f"📡 전송 중: {os.path.basename(p)}"))
                results = uploader.upload_to_targets(file_path)
                all_ok, any_ok, summary = self._summarize_upload_results(results)
                if all_ok:
                    self.root.after(0, lambda p=file_path, s=summary: self._log_message(f"🎉 성공: {os.path.basename(p)} ({s})"))
                    success_cnt += 1
                elif any_ok:
                    self.root.after(0, lambda p=file_path, s=summary: self._log_message(f"⚠️ 부분 성공: {os.path.basename(p)} ({s})"))
                    success_cnt += 1
                else:
                    self.root.after(0, lambda p=file_path, s=summary: self._log_message(f"❌ 실패: {os.path.basename(p)} ({s})"))
            self.root.after(0, lambda: self._calibre_send_finished(success_cnt, len(selected_items)))

        threading.Thread(target=task, daemon=True).start()

    def _calibre_send_finished(self, success_cnt: int, total_cnt: int):
        if not self._sync_busy:
            self.calibre_send_btn.config(state="normal")
        self._log_message(f"=== Calibre 도서 전송 종료: {success_cnt}/{total_cnt} 성공 ===\n")
        if success_cnt > 0:
            ToastNotifier.show_toast("Calibre 도서 동기화", f"{success_cnt}권 전송 완료.")
            messagebox.showinfo("완료", f"{success_cnt}권의 책이 전송되었습니다.")
        else:
            messagebox.showerror("오류", "전송에 실패했습니다. 기기 연결 상태를 확인하세요.")

    # ------------------------------------------------------------------
    # 다중 기기 관리
    # ------------------------------------------------------------------
    def _refresh_devices_tree(self):
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)
        for idx, dev in enumerate(self.service.config.get("x3_devices", [])):
            self.devices_tree.insert("", "end", iid=str(idx), values=(
                dev.get("name", ""), dev.get("ip", "")
            ))

    def _add_device_popup(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("X3 기기 추가")
        dialog.configure(bg=self.BG_COLOR)
        self._setup_dialog(dialog, 360, 180)
        frame = ttk.Frame(dialog, padding=15)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="기기 이름:").grid(row=0, column=0, sticky="w", pady=6)
        name_entry = ttk.Entry(frame, width=28)
        name_entry.grid(row=0, column=1, pady=6)
        ttk.Label(frame, text="IP/호스트:").grid(row=1, column=0, sticky="w", pady=6)
        ip_entry = ttk.Entry(frame, width=28)
        ip_entry.grid(row=1, column=1, pady=6)

        def save():
            name = name_entry.get().strip()
            ip = ip_entry.get().strip()
            if not name or not ip:
                messagebox.showerror("오류", "이름과 IP를 모두 입력해 주세요.", parent=dialog)
                return
            config = self.service.config
            devices = config.setdefault("x3_devices", [])
            if any(d.get("ip") == ip for d in devices):
                messagebox.showwarning("중복", "이미 등록된 IP입니다.", parent=dialog)
                return
            devices.append({"name": name, "ip": ip})
            self.service.config_manager.save_config(config)
            self.service._reload_config()
            self._refresh_devices_tree()
            dialog.destroy()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(fill="x", pady=8)
        ttk.Button(btn_frame, text="저장", command=save).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="취소", command=dialog.destroy).pack(side="right")

    def _remove_device(self):
        selected = self.devices_tree.selection()
        if not selected:
            messagebox.showwarning("경고", "삭제할 기기를 선택해 주세요.")
            return
        config = self.service.config
        devices = config.get("x3_devices", [])
        indices = sorted([int(i) for i in selected], reverse=True)
        for idx in indices:
            if 0 <= idx < len(devices):
                devices.pop(idx)
        config["x3_devices"] = devices
        self.service.config_manager.save_config(config)
        self.service._reload_config()
        self._refresh_devices_tree()

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
        dialog.configure(bg=self.BG_COLOR)
        self._setup_dialog(dialog, 560, 540)

        content = ttk.Frame(dialog)
        content.pack(fill="both", expand=True)

        frame = self._create_scrollable_frame(content)
        form = ttk.Frame(frame)
        form.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(form, text="사이트 이름:").grid(row=0, column=0, sticky="w", pady=8)
        name_entry = ttk.Entry(form, width=40)
        name_entry.grid(row=0, column=1, sticky="w", pady=8)

        ttk.Label(form, text="타입 (유형):").grid(row=1, column=0, sticky="w", pady=8)
        type_cb = ttk.Combobox(form, values=["css", "rss", "naver", "tistory", "brunch", "youtube", "substack"], state="readonly", width=12)
        type_cb.grid(row=1, column=1, sticky="w", pady=8)
        type_cb.set("css")

        ttk.Label(form, text="수집 주소(URL):").grid(row=2, column=0, sticky="w", pady=8)
        url_entry = ttk.Entry(form, width=40)
        url_entry.grid(row=2, column=1, sticky="w", pady=8)

        css_frame = ttk.LabelFrame(form, text=" CSS 선택자 설정 (CSS 타입 전용) ")
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

        ttk.Label(form, text="불필요 요소 제거 CSS:").grid(row=4, column=0, sticky="w", pady=8)
        remove_entry = ttk.Entry(form, width=40)
        remove_entry.grid(row=4, column=1, sticky="w", pady=8)

        ttk.Label(form, text="최대 수집 개수:").grid(row=5, column=0, sticky="w", pady=8)
        limit_entry = ttk.Entry(form, width=10)
        limit_entry.grid(row=5, column=1, sticky="w", pady=8)
        limit_entry.insert(0, "5")

        # 이미지 포함 / 번역 옵션
        opt_frame = ttk.Frame(form)
        opt_frame.grid(row=6, column=0, columnspan=2, sticky="we", pady=5)
        include_img_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="이미지 포함", variable=include_img_var).pack(side="left", padx=5)

        ttk.Label(opt_frame, text="번역:").pack(side="left", padx=(15, 3))
        translate_cb = ttk.Combobox(opt_frame, values=["", "ko", "en", "ja", "zh-cn", "zh-tw"], width=6)
        translate_cb.pack(side="left")
        translate_cb.set("")
        ttk.Label(opt_frame, text="(빈값=번역안함)", font=("Malgun Gothic", 8), foreground=self.HINT_COLOR).pack(side="left", padx=3)

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
            if not (url.startswith("http://") or url.startswith("https://")):
                messagebox.showerror("오류", "수집 주소는 http:// 또는 https://로 시작해야 합니다.", parent=dialog)
                return
            try:
                limit = int(limit_entry.get().strip())
            except ValueError:
                messagebox.showerror("오류", "수집 개수는 숫자여야 합니다.", parent=dialog)
                return
            if not (1 <= limit <= 50):
                messagebox.showerror("오류", "수집 개수는 1~50 사이여야 합니다.", parent=dialog)
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
        self._history_url_by_iid.clear()
        rows = self.service.db.get_history(limit=200)
        for row in rows:
            url = row[0]
            site_name = row[1] if len(row) > 1 else ""
            title = row[2] if len(row) > 2 else ""
            synced_at = row[3] if len(row) > 3 else ""
            devices = row[4] if len(row) > 4 else ""
            iid = hashlib.sha256((url or "").encode("utf-8")).hexdigest()[:24]
            self._history_url_by_iid[iid] = url
            display_title = title or ""
            if devices:
                display_title = f"{display_title} [{devices}]" if display_title else f"[{devices}]"
            self.hist_tree.insert("", "end", iid=iid, values=(
                site_name or "", display_title, synced_at or "", url or ""
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
        for iid in selected:
            url = self._history_url_by_iid.get(iid, iid)
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
            output_dir = resolve_path(self.dir_entry.get().strip() or "./output")
            allow_lan = self.opds_allow_lan_var.get()
            bind_host = "0.0.0.0" if allow_lan else "127.0.0.1"
            config = self.service.config_manager.load_config()
            opds_conf = config.get("opds_server", {})
            api_key = opds_conf.get("api_key", "")
            self._opds_server = OPDSServer(
                output_dir=output_dir,
                port=port,
                bind_host=bind_host,
                api_key=api_key,
                require_auth=allow_lan,
            )
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

            config = self.service.config_manager.load_config()
            web_conf = config.get("web_dashboard", {})
            api_token = web_conf.get("api_token", "")
            bind_host = "0.0.0.0" if self.web_allow_lan_var.get() else "127.0.0.1"

            def sync_cb():
                self.service.run_sync_pipeline(log_callback=self._make_log_callback())

            self._web_dashboard = WebDashboard(
                port=port,
                bind_host=bind_host,
                api_token=api_token,
                sync_callback=sync_cb,
                get_log_callback=self._get_log_for_web,
                pipeline_busy_callback=self.service.is_pipeline_running,
                get_status_callback=self.service.get_last_pipeline_result,
                allow_lan=self.web_allow_lan_var.get(),
            )
            if self.web_allow_lan_var.get():
                if not messagebox.askyesno(
                    "LAN 공개 경고",
                    "LAN 공개 모드는 HTTP 평문으로 API 토큰이 전송됩니다.\n"
                    "신뢰할 수 있는 네트워크에서만 계속하시겠습니까?",
                    icon="warning",
                ):
                    return
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
            def on_new_file(fpath: str):
                self._log_message(f"👁 새 파일 감지: {os.path.basename(fpath)} → 자동 전송 시작")
                def upload_task():
                    results = self._make_uploader().upload_to_targets(fpath)
                    all_ok, any_ok, summary = self._summarize_upload_results(results)
                    if all_ok:
                        msg = f"🎉 자동 전송 성공: {os.path.basename(fpath)} ({summary})"
                    elif any_ok:
                        msg = f"⚠️ 자동 부분 전송: {os.path.basename(fpath)} ({summary})"
                    else:
                        msg = f"❌ 자동 전송 실패: {os.path.basename(fpath)} ({summary})"
                    self.root.after(0, lambda m=msg: self._log_message(m))
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
        self._set_sync_ui_busy(True)
        self.progress_bar["value"] = 0
        self._log_message("\n=== 동기화 실행 요청 받음 ===")

        def run():
            self.service.run_sync_pipeline(
                log_callback=self._make_log_callback(),
                progress_callback=self._make_progress_callback(),
            )
            self.root.after(0, self._sync_finished_ui)

        threading.Thread(target=run, daemon=True).start()

    def _sync_finished_ui(self):
        maximum = float(self.progress_bar["maximum"] or 0)
        if maximum > 0:
            self.progress_bar["value"] = maximum
            self.root.after(1500, lambda: self.progress_bar.configure(value=0))
        else:
            self.progress_bar["value"] = 0
        self._set_sync_ui_busy(False)
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
