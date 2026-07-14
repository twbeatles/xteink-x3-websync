"""서버 & 고급 설정 탭 컴포넌트"""
import os
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


class SettingsTab(ttk.Frame):
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

        # 6. 로그 폴더 열기
        log_frame = ttk.LabelFrame(body, text=" 📂 로그 파일 ")
        log_frame.pack(fill="x", padx=15, pady=5)
        ttk.Button(log_frame, text="📂 로그 폴더 열기", command=self._open_log_folder).pack(side="left", padx=10, pady=8)
        ttk.Label(log_frame, text="logs/ 폴더에 날짜별 sync_YYYY-MM-DD.log 파일이 저장됩니다.", font=("Malgun Gothic", 8), foreground=HINT_COLOR).pack(side="left", padx=5, pady=8)

    # ------------------------------------------------------------------
    # M7 & M4: EPUB 설정 및 CSS 로딩
    # ------------------------------------------------------------------
    def _save_epub_settings(self):
        config = self.service.config
        config["epub_merge_mode"] = self.merge_mode_var.get()
        config["epub_theme"] = self.epub_theme_cb.get()
        config["epub_custom_css"] = self.custom_css_entry.get().strip()
        self.app._safe_save_config(config, reload=True)

    def _on_theme_changed(self, event=None):
        theme = self.epub_theme_cb.get()
        if theme == "custom":
            self.custom_css_entry.config(state="normal")
            self.custom_css_btn.config(state="normal")
        else:
            self.custom_css_entry.config(state="disabled")
            self.custom_css_btn.config(state="disabled")
        self._save_epub_settings()

    def _browse_custom_css(self):
        f = filedialog.askopenfilename(title="커스텀 CSS 파일 선택", filetypes=[("CSS files", "*.css"), ("All files", "*.*")])
        if f:
            self.custom_css_entry.config(state="normal")
            self.custom_css_entry.delete(0, tk.END)
            self.custom_css_entry.insert(0, f)
            self._save_epub_settings()
            if self.epub_theme_cb.get() != "custom":
                self.epub_theme_cb.set("custom")
                self._save_epub_settings()

    # ------------------------------------------------------------------
    # 서버 제어
    # ------------------------------------------------------------------
    def _toggle_opds(self):
        if self.app._opds_server and self.app._opds_server.is_running:
            self.app._opds_server.stop()
            self.app._opds_server = None
            self.opds_start_btn.config(text="▶ 서버 시작")
            self.opds_status_label.config(text="중지됨", foreground=RED_COLOR)
            self.opds_url_label.config(text="")
        else:
            try:
                port = int(self.opds_port_sp.get())
            except ValueError:
                port = 8765
            output_dir = resolve_path(self.app.tab_sync.dir_entry.get().strip() or "./output")
            allow_lan = self.opds_allow_lan_var.get()
            bind_host = "0.0.0.0" if allow_lan else "127.0.0.1"
            config = self.config_manager.load_config()
            opds_conf = config.get("opds_server", {})
            api_key = opds_conf.get("api_key", "")
            self.app._opds_server = OPDSServer(
                output_dir=output_dir,
                port=port,
                bind_host=bind_host,
                api_key=api_key,
                require_auth=allow_lan,
            )
            if self.app._opds_server.start():
                self.opds_start_btn.config(text="■ 서버 중지")
                self.opds_status_label.config(text="실행 중 ✅", foreground=GREEN_COLOR)
                url = self.app._opds_server.get_url()
                self.opds_url_label.config(text=url)
                self.app._log_message(f"📡 OPDS 서버 시작: {url}")
            else:
                messagebox.showerror("오류", f"OPDS 서버 시작 실패. 포트 {port}이 이미 사용 중일 수 있습니다.")

    def _toggle_web(self):
        if self.app._web_dashboard and self.app._web_dashboard.is_running:
            self.app._web_dashboard.stop()
            self.app._web_dashboard = None
            self.web_start_btn.config(text="▶ 서버 시작")
            self.web_status_label.config(text="중지됨", foreground=RED_COLOR)
            self.web_url_label.config(text="")
        else:
            try:
                port = int(self.web_port_sp.get())
            except ValueError:
                port = 8766

            config = self.config_manager.load_config()
            web_conf = config.get("web_dashboard", {})
            api_token = web_conf.get("api_token", "")
            bind_host = "0.0.0.0" if self.web_allow_lan_var.get() else "127.0.0.1"

            def sync_cb():
                self.service.run_sync_pipeline(log_callback=self.app._make_log_callback())

            self.app._web_dashboard = WebDashboard(
                port=port,
                bind_host=bind_host,
                api_token=api_token,
                sync_callback=sync_cb,
                get_log_callback=self.app._get_log_for_web,
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
            if self.app._web_dashboard.start():
                self.web_start_btn.config(text="■ 서버 중지")
                self.web_status_label.config(text="실행 중 ✅", foreground=GREEN_COLOR)
                url = self.app._web_dashboard.get_url()
                self.web_url_label.config(text=url)
                self.app._log_message(f"🌐 웹 대시보드 시작: {url}")
            else:
                messagebox.showerror("오류", f"웹 대시보드 시작 실패. 포트 {port}이 이미 사용 중일 수 있습니다.")

    def _toggle_watch(self):
        if self.app._calibre_watcher and self.app._calibre_watcher.is_running:
            self.app._calibre_watcher.stop()
            self.app._calibre_watcher = None
            self.watch_start_btn.config(text="▶ 감시 시작")
            self.watch_status_label.config(text="감시 중지됨", foreground=RED_COLOR)
        else:
            watch_dir = self.watch_dir_entry.get().strip()
            if not watch_dir or not os.path.isdir(watch_dir):
                messagebox.showerror("오류", "유효한 감시 폴더를 선택해 주세요.")
                return
            def on_new_file(fpath: str):
                self.app._log_message(f"👁 새 파일 감지: {os.path.basename(fpath)} → 자동 전송 대기 중")
                def upload_task():
                    pipeline_acquired = False
                    process_acquired = False
                    try:
                        # 파이프라인 락 및 프로세스 락 순차 획득 (데드락 방지 차원)
                        pipeline_acquired = self.service._pipeline_lock.acquire(blocking=True)
                        process_acquired = self.service._process_lock.acquire(blocking=True)

                        self.app.root.after(0, lambda: self.app._log_message(f"📡 자동 전송 시작: {os.path.basename(fpath)}"))
                        results = self.app._make_uploader().upload_to_targets(fpath)
                        all_ok, any_ok, summary = self.app._summarize_upload_results(results)
                        if all_ok:
                            msg = f"🎉 자동 전송 성공: {os.path.basename(fpath)} ({summary})"
                        elif any_ok:
                            msg = f"⚠️ 자동 부분 전송: {os.path.basename(fpath)} ({summary})"
                        else:
                            msg = f"❌ 자동 전송 실패: {os.path.basename(fpath)} ({summary})"
                        self.app.root.after(0, lambda m=msg: self.app._log_message(m))
                    finally:
                        if process_acquired:
                            self.service._process_lock.release()
                        if pipeline_acquired:
                            self.service._pipeline_lock.release()
                threading.Thread(target=upload_task, daemon=True).start()


            self.app._calibre_watcher = CalibreWatcher(watch_dir, on_new_file)
            if self.app._calibre_watcher.start():
                self.watch_start_btn.config(text="■ 감시 중지")
                self.watch_status_label.config(text=f"✅ 감시 중: {watch_dir}", foreground=GREEN_COLOR)
                self.app._log_message(f"👁 Calibre Watch 시작: {watch_dir}")
                config = self.service.config
                config["calibre_watch"] = {"enabled": True, "watch_dir": watch_dir}
                self.app._safe_save_config(config)
            else:
                messagebox.showerror("오류", "파일 감시 시작 실패. watchdog 패키지가 설치되어 있는지 확인하세요.")

    def _browse_watch_dir(self):
        d = filedialog.askdirectory(title="감시할 Calibre 라이브러리 폴더 선택")
        if d:
            self.watch_dir_entry.delete(0, tk.END)
            self.watch_dir_entry.insert(0, d)
            self.app._save_ui_settings()

    def _open_log_folder(self):
        folder = get_log_dir()
        os.makedirs(folder, exist_ok=True)
        try:
            if os.name == "nt":
                os.startfile(folder)
            elif os.sys.platform == "darwin":
                import subprocess
                subprocess.Popen(["open", folder])
            else:
                import subprocess
                subprocess.Popen(["xdg-open", folder])
        except Exception as e:
            messagebox.showerror("오류", f"로그 폴더를 열 수 없습니다: {e}")

    def _save_ai_settings(self):
        config = self.service.config
        config["ai_summary"] = {
            "enabled": self.ai_enabled_var.get(),
            "provider": self.ai_provider_cb.get(),
            "api_key": self.ai_key_entry.get().strip(),
            "model": config.get("ai_summary", {}).get("model", "gpt-4o-mini"),
            "ollama_host": config.get("ai_summary", {}).get("ollama_host", "http://localhost:11434"),
        }
        if not self.app._safe_save_config(config):
            return
        messagebox.showinfo("저장 완료", "AI 요약 설정이 저장되었습니다.")

    def _save_trans_settings(self):
        config = self.service.config
        config["translation"] = {
            "enabled": self.trans_enabled_var.get(),
            "provider": self.trans_provider_cb.get(),
            "libretranslate_host": config.get("translation", {}).get("libretranslate_host", "http://localhost:5000"),
            "libretranslate_api_key": config.get("translation", {}).get("libretranslate_api_key", ""),
        }
        if not self.app._safe_save_config(config):
            return
        messagebox.showinfo("저장 완료", "번역 설정이 저장되었습니다.")
