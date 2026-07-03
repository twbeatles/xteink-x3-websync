import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from calibre import CalibreManager
from uploader import X3Uploader
from scheduler import SchedulerManager
from notifier import ToastNotifier
from service import SyncService

class SyncAppGui:
    """Tkinter를 기반으로 탭형 인터페이스를 제공하고 비즈니스 흐름을 연동하는 클래스"""
    def __init__(self, service: SyncService):
        self.service = service
        self.scheduler = SchedulerManager()
        self.calibre = CalibreManager(self.service.config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"))
        
        self.root = tk.Tk()
        self.root.title("Xteink X3 WebSync Manager")
        self.root.geometry("820x720")
        self.root.resizable(False, False)
        
        self._setup_styles()
        self._build_ui()
        self._load_config_to_ui()

    def _setup_styles(self):
        # 다크 테마 색상 정의 (Sleek dark mode)
        self.style = ttk.Style()
        self.style.theme_use('clam')
        
        self.BG_COLOR = "#1e1e2e"
        self.FG_COLOR = "#cdd6f4"
        self.ACCENT_COLOR = "#89b4fa"
        self.SECONDARY_BG = "#313244"
        self.TEXT_BG = "#181825"
        self.GREEN_COLOR = "#a6e3a1"
        self.RED_COLOR = "#f38ba8"

        self.root.configure(bg=self.BG_COLOR)

        self.style.configure(".", background=self.BG_COLOR, foreground=self.FG_COLOR, font=("Malgun Gothic", 9))
        self.style.configure("TFrame", background=self.BG_COLOR)
        
        # Notebook (탭) 스타일 설정
        self.style.configure("TNotebook", background=self.BG_COLOR, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=self.SECONDARY_BG, foreground=self.FG_COLOR, padding=[12, 6], font=("Malgun Gothic", 9, "bold"))
        self.style.map("TNotebook.Tab", 
            background=[("selected", self.BG_COLOR)], 
            foreground=[("selected", self.ACCENT_COLOR)]
        )

        self.style.configure("TLabelframe", background=self.BG_COLOR, foreground=self.ACCENT_COLOR, bordercolor=self.SECONDARY_BG)
        self.style.configure("TLabelframe.Label", background=self.BG_COLOR, foreground=self.ACCENT_COLOR, font=("Malgun Gothic", 10, "bold"))
        
        self.style.configure("TLabel", background=self.BG_COLOR, foreground=self.FG_COLOR)
        
        self.style.configure("TButton", background=self.SECONDARY_BG, foreground=self.FG_COLOR, bordercolor=self.SECONDARY_BG, relief="flat", padding=5)
        self.style.map("TButton", 
            background=[("active", self.ACCENT_COLOR), ("disabled", self.SECONDARY_BG)],
            foreground=[("active", self.BG_COLOR), ("disabled", "#585b70")]
        )
        
        self.style.configure("Treeview", background=self.TEXT_BG, fieldbackground=self.TEXT_BG, foreground=self.FG_COLOR, bordercolor=self.SECONDARY_BG, rowheight=24)
        self.style.map("Treeview", background=[("selected", self.ACCENT_COLOR)], foreground=[("selected", self.BG_COLOR)])
        self.style.configure("Treeview.Heading", background=self.SECONDARY_BG, foreground=self.FG_COLOR, bordercolor=self.SECONDARY_BG, font=("Malgun Gothic", 9, "bold"))

    def _build_ui(self):
        # 탭 컨트롤 생성
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=10, pady=10)

        # 탭 정의
        self.tab_sync = ttk.Frame(self.notebook)
        self.tab_calibre = ttk.Frame(self.notebook)

        self.notebook.add(self.tab_sync, text=" 뉴스 동기화 및 일반설정 ")
        self.notebook.add(self.tab_calibre, text=" Calibre 서재 연동 ")

        # ------------------------------------
        # [탭 1] 일반 설정 및 뉴스 동기화 화면
        # ------------------------------------
        
        # 기기 및 저장 경로 프레임
        settings_frame = ttk.LabelFrame(self.tab_sync, text=" 기기 및 경로 설정 ")
        settings_frame.pack(fill="x", padx=15, pady=8)

        # IP/호스트명 라벨로 유연성 증대 (crosspoint.local 안내 포함)
        ttk.Label(settings_frame, text="X3 주소 (IP/호스트):").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.ip_entry = ttk.Entry(settings_frame, width=22, font=("Consolas", 10))
        self.ip_entry.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        
        self.test_conn_btn = ttk.Button(settings_frame, text="연결 확인", command=self._test_connection)
        self.test_conn_btn.grid(row=0, column=2, padx=5, pady=6)

        self.conn_status_label = ttk.Label(settings_frame, text="미확인", foreground="#f9e2af")
        self.conn_status_label.grid(row=0, column=3, padx=10, pady=6, sticky="w")

        ttk.Label(settings_frame, text="출력 저장 폴더:").grid(row=1, column=0, padx=10, pady=6, sticky="w")
        self.dir_entry = ttk.Entry(settings_frame, width=45)
        self.dir_entry.grid(row=1, column=1, columnspan=2, padx=5, pady=6, sticky="we")
        
        dir_btn = ttk.Button(settings_frame, text="폴더 선택", command=self._browse_directory)
        dir_btn.grid(row=1, column=3, padx=5, pady=6)

        # 폰트 및 스타일 상세 제어 프레임
        font_frame = ttk.LabelFrame(self.tab_sync, text=" 한국어 가독성 스타일 최적화 (EPUB 포맷팅) ")
        font_frame.pack(fill="x", padx=15, pady=5)

        ttk.Label(font_frame, text="본문 글꼴(폰트 패밀리):").grid(row=0, column=0, padx=10, pady=6, sticky="w")
        self.font_cb = ttk.Combobox(font_frame, values=["serif", "sans-serif", "KoPubWorldBatang", "NanumGothic", "Malgun Gothic"], width=15)
        self.font_cb.grid(row=0, column=1, padx=5, pady=6, sticky="w")
        self.font_cb.set("serif")

        ttk.Label(font_frame, text="글자 크기 (px):").grid(row=0, column=2, padx=15, pady=6, sticky="w")
        self.font_size_sp = ttk.Spinbox(font_frame, from_=10, to=30, width=5)
        self.font_size_sp.grid(row=0, column=3, padx=5, pady=6, sticky="w")
        self.font_size_sp.set("16")

        ttk.Label(font_frame, text="줄 간격 (Line Height):").grid(row=0, column=4, padx=15, pady=6, sticky="w")
        self.line_height_sp = ttk.Spinbox(font_frame, from_=1.0, to=3.0, increment=0.1, width=5)
        self.line_height_sp.grid(row=0, column=5, padx=5, pady=6, sticky="w")
        self.line_height_sp.set("1.7")

        # 뉴스 리스트 뷰 및 관리 프레임
        sites_frame = ttk.LabelFrame(self.tab_sync, text=" 동기화 대상 사이트 관리 ")
        sites_frame.pack(fill="both", expand=True, padx=15, pady=5)

        columns = ("name", "type", "enabled", "url")
        self.tree = ttk.Treeview(sites_frame, columns=columns, show="headings")
        self.tree.heading("name", text="사이트 이름")
        self.tree.heading("type", text="유형")
        self.tree.heading("enabled", text="활성화")
        self.tree.heading("url", text="URL")
        
        self.tree.column("name", width=140, anchor="w")
        self.tree.column("type", width=55, anchor="center")
        self.tree.column("enabled", width=55, anchor="center")
        self.tree.column("url", width=380, anchor="w")
        
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

        # 로컬 직접 전송 및 스케줄러 영역 (하단 그리드)
        bottom_grid = ttk.Frame(self.tab_sync)
        bottom_grid.pack(fill="x", padx=15, pady=5)
        bottom_grid.columnconfigure(0, weight=1)
        bottom_grid.columnconfigure(1, weight=1)

        # 파일 전송
        upload_frame = ttk.LabelFrame(bottom_grid, text=" 로컬 파일 X3 직접 전송 ")
        upload_frame.grid(row=0, column=0, padx=(0, 5), sticky="nswe")

        self.file_entry = ttk.Entry(upload_frame, width=28)
        self.file_entry.grid(row=0, column=0, padx=8, pady=10, sticky="we")
        
        file_select_btn = ttk.Button(upload_frame, text="...", width=3, command=self._browse_file)
        file_select_btn.grid(row=0, column=1, padx=3, pady=10)

        self.direct_upload_btn = ttk.Button(upload_frame, text="기기로 직접 전송", command=self._direct_upload)
        self.direct_upload_btn.grid(row=0, column=2, padx=8, pady=10)

        # 윈도우 스케줄러
        scheduler_frame = ttk.LabelFrame(bottom_grid, text=" 자동 스케줄 설정 (윈도우) ")
        scheduler_frame.grid(row=0, column=1, padx=(5, 0), sticky="nswe")

        ttk.Label(scheduler_frame, text="매일 시간:").grid(row=0, column=0, padx=8, pady=10, sticky="w")
        
        self.hour_cb = ttk.Combobox(scheduler_frame, values=[f"{i:02d}" for i in range(24)], width=3, state="readonly")
        self.hour_cb.grid(row=0, column=1, padx=2, pady=10)
        
        self.min_cb = ttk.Combobox(scheduler_frame, values=[f"{i:02d}" for i in range(60)], width=3, state="readonly")
        self.min_cb.grid(row=0, column=2, padx=2, pady=10)

        self.sched_reg_btn = ttk.Button(scheduler_frame, text="등록", command=self._register_schedule)
        self.sched_reg_btn.grid(row=0, column=3, padx=3, pady=10)
        
        self.sched_unreg_btn = ttk.Button(scheduler_frame, text="해제", command=self._unregister_schedule)
        self.sched_unreg_btn.grid(row=0, column=4, padx=3, pady=10)

        self.sched_status_label = ttk.Label(scheduler_frame, text="스케줄 확인 중...", font=("Malgun Gothic", 8))
        self.sched_status_label.grid(row=1, column=0, columnspan=5, padx=8, pady=(0, 6), sticky="w")

        # ------------------------------------
        # [탭 2] Calibre 서재 연동 화면
        # ------------------------------------
        
        calibre_top_frame = ttk.LabelFrame(self.tab_calibre, text=" Calibre 연동 설정 ")
        calibre_top_frame.pack(fill="x", padx=15, pady=10)

        ttk.Label(calibre_top_frame, text="calibredb.exe 경로:").grid(row=0, column=0, padx=10, pady=8, sticky="w")
        self.calibre_entry = ttk.Entry(calibre_top_frame, width=50)
        self.calibre_entry.grid(row=0, column=1, padx=5, pady=8, sticky="we")
        
        calibre_browse_btn = ttk.Button(calibre_top_frame, text="찾아보기", command=self._browse_calibredb)
        calibre_browse_btn.grid(row=0, column=2, padx=5, pady=8)

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

        self.calibre_send_btn = ttk.Button(calibre_action_frame, text="★ 선택한 도서 X3 기기로 즉시 전송 시작 (다중 선택 가능)", command=self._send_calibre_books)
        self.calibre_send_btn.pack(fill="x", pady=5)

        # ------------------------------------
        # 메인 프레임 공통 하단 요소
        # ------------------------------------
        sync_run_frame = ttk.Frame(self.root)
        sync_run_frame.pack(fill="x", padx=15, pady=2)

        self.sync_now_btn = ttk.Button(sync_run_frame, text="🚀 즉시 전체 뉴스 스크래핑 및 X3 동기화 실행", command=self._run_immediate_sync)
        self.sync_now_btn.pack(fill="x", pady=3)

        log_frame = ttk.LabelFrame(self.root, text=" 프로그램 상태 및 동기화 로그 ")
        log_frame.pack(fill="both", expand=False, padx=15, pady=(2, 10))

        self.log_txt = tk.Text(log_frame, height=6, bg=self.TEXT_BG, fg=self.FG_COLOR, insertbackground=self.FG_COLOR, font=("Consolas", 9))
        self.log_txt.pack(fill="both", expand=True, padx=8, pady=8)
        self.log_txt.config(state="disabled")

    def _log_message(self, message: str):
        self.log_txt.config(state="normal")
        self.log_txt.insert(tk.END, message + "\n")
        self.log_txt.see(tk.END)
        self.log_txt.config(state="disabled")

    def _load_config_to_ui(self):
        config = self.service.config
        self.ip_entry.insert(0, config.get("x3_ip", "crosspoint.local"))
        self.dir_entry.insert(0, config.get("output_dir", "./output"))
        self.calibre_entry.insert(0, config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"))
        
        self.font_cb.set(config.get("font_family", "serif"))
        self.font_size_sp.set(str(config.get("font_size", 16)))
        self.line_height_sp.set(str(config.get("line_height", 1.7)))
        
        sched_conf = config.get("schedule", {})
        self.hour_cb.set(sched_conf.get("hour", "07"))
        self.min_cb.set(sched_conf.get("minute", "00"))

        self._refresh_site_tree()
        self._refresh_schedule_status()
        
        threading.Thread(target=self._test_and_load_calibre, kwargs={"silent": True}, daemon=True).start()

    def _refresh_site_tree(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
            
        config = self.service.config
        for idx, site in enumerate(config.get("sites", [])):
            enabled_str = "V" if site.get("enabled", True) else "-"
            self.tree.insert("", "end", iid=str(idx), values=(
                site.get("name"),
                site.get("type", "css").upper(),
                enabled_str,
                site.get("url")
            ))

    def _refresh_schedule_status(self):
        status = self.scheduler.get_task_status()
        self.sched_status_label.config(text=f"현재 윈도우 스케줄러 상태: {status}")

    def _save_ui_settings(self):
        config = self.service.config
        config["x3_ip"] = self.ip_entry.get().strip()
        config["output_dir"] = self.dir_entry.get().strip()
        config["calibre_path"] = self.calibre_entry.get().strip()
        config["font_family"] = self.font_cb.get()
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

    def _browse_directory(self):
        selected_dir = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if selected_dir:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, selected_dir)
            self._save_ui_settings()

    def _browse_file(self):
        selected_file = filedialog.askopenfilename(
            title="X3로 전송할 파일 선택",
            filetypes=[("eBook files", "*.epub;*.pdf;*.txt;*.mobi"), ("All files", "*.*")]
        )
        if selected_file:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, selected_file)

    def _browse_calibredb(self):
        selected_file = filedialog.askopenfilename(
            title="calibredb.exe 실행파일 찾기",
            filetypes=[("Executable", "calibredb.exe"), ("All files", "*.*")]
        )
        if selected_file:
            self.calibre_entry.delete(0, tk.END)
            self.calibre_entry.insert(0, selected_file)
            self._save_ui_settings()

    def _test_connection(self):
        ip = self.ip_entry.get().strip()
        self.conn_status_label.config(text="연결 중...", foreground="#f9e2af")
        self.root.update_idletasks()
        
        uploader = X3Uploader(ip)
        if uploader.test_connection():
            self.conn_status_label.config(text="연결 성공", foreground=self.GREEN_COLOR)
        else:
            self.conn_status_label.config(text="연결 실패", foreground=self.RED_COLOR)

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
            uploader = X3Uploader(ip)
            success = uploader.upload(file_path)
            self.root.after(0, lambda: self._direct_upload_finished(success, file_path))

        threading.Thread(target=task, daemon=True).start()

    def _direct_upload_finished(self, success: bool, file_path: str):
        self.direct_upload_btn.config(state="normal")
        if success:
            self._log_message(f"🎉 파일 전송 성공: {os.path.basename(file_path)}")
            ToastNotifier.show_toast("파일 업로드 성공", f"로컬 파일 '{os.path.basename(file_path)}'이 정상 전송되었습니다.")
            messagebox.showinfo("완료", "기기로 전송이 완료되었습니다.")
        else:
            self._log_message(f"❌ 파일 전송 실패: {os.path.basename(file_path)}")
            self._log_message("💡 팁: 기기 전원이 켜져 있고 Wi-Fi 상태인지 확인해 주세요. (절전 모드 시 와이파이가 차단됩니다.)")
            ToastNotifier.show_toast("파일 업로드 실패", f"기기 전송 과정에 오류가 발생했습니다. (기기 연결 상태 확인 요망)", is_error=True)
            messagebox.showerror("오류", "기기로 전송하지 못했습니다. IP/호스트명 및 Wi-Fi 전원 상태를 확인하세요.")

    def _register_schedule(self):
        self._save_ui_settings()
        h = self.hour_cb.get()
        m = self.min_cb.get()
        
        if self.scheduler.register_daily_task(h, m):
            messagebox.showinfo("스케줄러", f"매일 {h}:{m}에 백그라운드 동기화 스케줄이 정상 등록되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = True
            self.service.config_manager.save_config(config)
        else:
            messagebox.showerror("스케줄러", "윈도우 작업 스케줄러 등록에 실패했습니다. 권한 등을 확인하세요.")
        self._refresh_schedule_status()

    def _unregister_schedule(self):
        if self.scheduler.unregister_task():
            messagebox.showinfo("스케줄러", "스케줄 작업이 정상 해제되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = False
            self.service.config_manager.save_config(config)
        else:
            messagebox.showwarning("스케줄러", "스케줄 작업 해제에 실패했거나 등록된 작업이 없습니다.")
        self._refresh_schedule_status()

    def _test_and_load_calibre(self, silent=False):
        self._save_ui_settings()
        self.calibre.calibre_path = self.calibre_entry.get().strip()
        
        if not silent:
            self._log_message("📚 Calibre 실행 파일 검증 및 라이브러리 목록 갱신을 시작합니다...")
            self.calibre_conn_btn.config(state="disabled")
            self.root.update_idletasks()

        if not self.calibre.test_connection():
            if not silent:
                self._log_message("❌ Calibre 연동 실패: calibredb.exe 파일 경로가 올바르지 않습니다.")
                messagebox.showerror("Calibre 연동 실패", "calibredb.exe 경로를 찾지 못했거나 실행에 실패했습니다. 설치 경로를 확인하세요.")
                self.calibre_conn_btn.config(state="normal")
            return

        def load():
            books = self.calibre.list_books()
            self.root.after(0, lambda: self._show_calibre_books(books, silent))

        threading.Thread(target=load, daemon=True).start()

    def _show_calibre_books(self, books: list, silent: bool):
        self.calibre_conn_btn.config(state="normal")
        
        for item in self.calibre_tree.get_children():
            self.calibre_tree.delete(item)

        if not books:
            if not silent:
                self._log_message("⚠️ Calibre 연동 성공하였으나 등록된 책이 없거나 조회가 실패했습니다.")
            return

        for bk in books:
            bk_id = bk.get("id")
            title = bk.get("title")
            authors = bk.get("authors", "")
            formats = bk.get("formats", "")
            
            if isinstance(formats, list):
                formats_str = ", ".join(formats)
            else:
                formats_str = str(formats)

            self.calibre_tree.insert("", "end", iid=str(bk_id), values=(
                bk_id, title, authors, formats_str
            ))
            
        if not silent:
            self._log_message(f"🎉 Calibre 서재 동기화 완료: {len(books)}권의 책을 성공적으로 읽어왔습니다.")
            ToastNotifier.show_toast("Calibre 연동 성공", f"서재에서 {len(books)}권의 책 정보를 불러왔습니다.")

    def _send_calibre_books(self):
        selected_items = self.calibre_tree.selection()
        if not selected_items:
            messagebox.showwarning("선택 누락", "X3 기기로 보낼 도서를 선택해 주세요.")
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
                    self.root.after(0, lambda b=book_id: self._log_message(f"❌ [책 ID {b}] 실제 파일 경로를 조회하지 못했거나 파일이 유실되었습니다."))
                    continue
                
                self.root.after(0, lambda p=file_path: self._log_message(f"📡 전송 파일 검색 성공 => {os.path.basename(p)} 업로드 중..."))
                
                if uploader.upload(file_path):
                    self.root.after(0, lambda p=file_path: self._log_message(f"🎉 성공: {os.path.basename(p)} 전송 완료"))
                    success_cnt += 1
                else:
                    self.root.after(0, lambda p=file_path: self._log_message(f"❌ 실패: {os.path.basename(p)} 업로드 실패"))

            self.root.after(0, lambda: self._calibre_send_finished(success_cnt, len(selected_items)))

        threading.Thread(target=task, daemon=True).start()

    def _calibre_send_finished(self, success_cnt: int, total_cnt: int):
        self.calibre_send_btn.config(state="normal")
        self._log_message(f"=== Calibre 도서 전송 종료: {success_cnt}/{total_cnt} 성공 ===\n")
        
        if success_cnt > 0:
            ToastNotifier.show_toast("Calibre 도서 동기화", f"{total_cnt}권 중 {success_cnt}권 도서 무선 전송 완료.")
            messagebox.showinfo("완료", f"{success_cnt}권의 책이 정상적으로 전송되었습니다.")
        else:
            ToastNotifier.show_toast("Calibre 도서 동기화 실패", "X3 기기로 책 전송을 실패했습니다. IP 및 와이파이를 확인하세요.", is_error=True)
            messagebox.showerror("오류", "선택한 책 전송에 실패했습니다. 기기 IP 혹은 와이파이 연결 상태를 확인하세요.")

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

        if not messagebox.askyesno("확인", "선택한 사이트를 목록에서 정말 삭제하시겠습니까?"):
            return

        config = self.service.config
        idx = int(selected[0])
        config["sites"].pop(idx)
        
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
        site = self.service.config["sites"][idx]
        self._open_site_dialog("사이트 수정", idx, site)

    def _open_site_dialog(self, title: str, idx: int = None, site_data: dict = None):
        dialog = tk.Toplevel(self.root)
        dialog.title(title)
        dialog.geometry("520x460")
        dialog.resizable(False, False)
        dialog.configure(bg=self.BG_COLOR)
        dialog.grab_set()

        frame = ttk.Frame(dialog)
        frame.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(frame, text="사이트 이름:").grid(row=0, column=0, sticky="w", pady=8)
        name_entry = ttk.Entry(frame, width=40)
        name_entry.grid(row=0, column=1, sticky="w", pady=8)

        ttk.Label(frame, text="타입 (유형):").grid(row=1, column=0, sticky="w", pady=8)
        type_cb = ttk.Combobox(frame, values=["css", "rss"], state="readonly", width=10)
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
        remove_entry.insert(0, "")
        
        help_lbl = ttk.Label(frame, text="* 쉼표(,) 구분. 광고 배너, 댓글 영역의 CSS 클래스/아이디 명시 (예: .ad, #comments)", font=("Malgun Gothic", 8), foreground="#a6adc8")
        help_lbl.grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 8))

        ttk.Label(frame, text="최대 수집 개수:").grid(row=6, column=0, sticky="w", pady=8)
        limit_entry = ttk.Entry(frame, width=10)
        limit_entry.grid(row=6, column=1, sticky="w", pady=8)
        limit_entry.insert(0, "5")

        def on_type_change(event):
            t = type_cb.get()
            if t == "rss":
                item_entry.config(state="disabled")
                title_entry.config(state="disabled")
                content_entry.config(state="disabled")
                remove_entry.config(state="disabled")
            else:
                item_entry.config(state="normal")
                title_entry.config(state="normal")
                content_entry.config(state="normal")
                remove_entry.config(state="normal")

        type_cb.bind("<<ComboboxSelected>>", on_type_change)

        if site_data:
            name_entry.insert(0, site_data.get("name", ""))
            type_cb.set(site_data.get("type", "css"))
            url_entry.insert(0, site_data.get("url", ""))
            item_entry.delete(0, tk.END)
            item_entry.insert(0, site_data.get("item_selector", ".post-item"))
            title_entry.delete(0, tk.END)
            title_entry.insert(0, site_data.get("title_selector", ".post-title"))
            content_entry.delete(0, tk.END)
            content_entry.insert(0, site_data.get("content_selector", ".post-content"))
            remove_entry.delete(0, tk.END)
            remove_entry.insert(0, site_data.get("remove_selectors", ""))
            limit_entry.delete(0, tk.END)
            limit_entry.insert(0, str(site_data.get("limit", 5)))
            on_type_change(None)

        def save_site():
            name = name_entry.get().strip()
            url = url_entry.get().strip()
            limit_str = limit_entry.get().strip()

            if not name or not url:
                messagebox.showerror("오류", "이름과 수집 주소는 필수값입니다.", parent=dialog)
                return
            
            try:
                limit = int(limit_str)
            except ValueError:
                messagebox.showerror("오류", "수집 개수는 숫자여야 합니다.", parent=dialog)
                return

            config = self.service.config
            new_site = {
                "name": name,
                "type": type_cb.get(),
                "url": url,
                "limit": limit,
                "enabled": site_data.get("enabled", True) if site_data else True
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

    def _run_immediate_sync(self):
        self._save_ui_settings()
        self.sync_now_btn.config(state="disabled")
        self._log_message("\n=== 동기화 실행 요청 받음 ===")
        
        def run():
            success = self.service.run_sync_pipeline(log_callback=lambda msg: self.root.after(0, lambda: self._log_message(msg)))
            self.root.after(0, lambda: self._sync_finished(success))

        threading.Thread(target=run, daemon=True).start()

    def _sync_finished(self, success: bool):
        self.sync_now_btn.config(state="normal")
        self._log_message("=== 동기화 프로세스 종료 ===\n")
        if success:
            messagebox.showinfo("동기화 완료", "지정한 사이트의 기사 수집 및 X3 전송이 모두 완료되었습니다.")
        else:
            messagebox.showwarning("동기화 주의", "수집 혹은 전송 과정에 오류가 발생했거나, 활성화된 사이트가 없습니다. 로그를 확인해 주세요.")

    def run(self):
        self.root.mainloop()
