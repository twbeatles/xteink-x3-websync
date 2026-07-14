"""뉴스 동기화 탭 컴포넌트"""
import os
import hashlib
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.gui.widgets import (
    BG_COLOR, TEXT_BG, SECONDARY_BG, HINT_COLOR, YELLOW_COLOR, GREEN_COLOR, RED_COLOR,
    create_scrollable_frame, create_scrolled_tree, setup_dialog, bind_widget_mousewheel
)
from websync.upload.uploader import X3Uploader
from websync.config.exceptions import ConfigSaveError, ConfigLoadError


class SyncTab(ttk.Frame):
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
    def _test_connection(self):
        self.conn_status_label.config(text="연결 중...", foreground=YELLOW_COLOR)
        self.test_conn_btn.config(state="disabled")

        def task():
            uploader = self.app._make_uploader()
            results = []
            for dev in uploader._build_target_list():
                ok = uploader.test_connection(dev["ip"])
                results.append((dev["name"], dev["ip"], ok))
            self.master.after(0, lambda: self._test_connection_finished(results))

        threading.Thread(target=task, daemon=True).start()

    def _test_connection_finished(self, results: list[tuple[str, str, bool]]):
        if not self.app._sync_busy:
            self.test_conn_btn.config(state="normal")
        if not results:
            self.conn_status_label.config(text="등록된 기기 없음", foreground=RED_COLOR)
            return
        ok_count = sum(1 for _, _, ok in results if ok)
        if ok_count == len(results):
            self.conn_status_label.config(text=f"전체 {len(results)}대 연결 성공 ✅", foreground=GREEN_COLOR)
        elif ok_count > 0:
            failed = [name for name, _, ok in results if not ok]
            self.conn_status_label.config(
                text=f"부분 성공 ({ok_count}/{len(results)}) — 실패: {', '.join(failed)}",
                foreground=YELLOW_COLOR,
            )
        else:
            self.conn_status_label.config(text="모든 기기 연결 실패 ❌", foreground=RED_COLOR)
        for name, ip, ok in results:
            status = "✅" if ok else "❌"
            self.app._log_message(f"   {status} [{name}] {ip}")

    def _browse_directory(self):
        d = filedialog.askdirectory(initialdir=self.dir_entry.get())
        if d:
            self.dir_entry.delete(0, tk.END)
            self.dir_entry.insert(0, d)
            self.app._save_ui_settings()

    def _browse_file(self):
        f = filedialog.askopenfilename(title="X3로 전송할 파일 선택", filetypes=[("eBook files", "*.epub;*.pdf;*.txt;*.mobi"), ("All files", "*.*")])
        if f:
            self.file_entry.delete(0, tk.END)
            self.file_entry.insert(0, f)

    def _open_output_folder(self):
        folder = self.dir_entry.get().strip() or "./output"
        folder = os.path.abspath(folder)
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
            messagebox.showerror("오류", f"폴더를 열 수 없습니다: {e}")

    def _direct_upload(self):
        file_path = self.file_entry.get().strip()
        if not file_path or not os.path.exists(file_path):
            messagebox.showwarning("경고", "올바른 파일 경로를 지정해 주세요.")
            return
        self.app._save_ui_settings()
        self.app._log_message(f"📡 로컬 파일 직접 전송 중: {os.path.basename(file_path)}")
        self.direct_upload_btn.config(state="disabled")

        def task():
            results = self.app._make_uploader().upload_to_targets(file_path)
            self.master.after(0, lambda: self._direct_upload_finished(results, file_path))

        threading.Thread(target=task, daemon=True).start()

    def _direct_upload_finished(self, results: dict, file_path: str):
        if not self.app._sync_busy:
            self.direct_upload_btn.config(state="normal")
        all_ok, any_ok, summary = self.app._summarize_upload_results(results)
        basename = os.path.basename(file_path)
        if all_ok:
            self.app._log_message(f"🎉 파일 전송 성공 ({basename}): {summary}")
            from websync.integrations.notifier import ToastNotifier
            ToastNotifier.show_toast("파일 업로드 성공", f"'{basename}' 전송 완료.")
            messagebox.showinfo("완료", f"모든 기기로 전송 완료.\n{summary}")
        elif any_ok:
            self.app._log_message(f"⚠️ 파일 부분 전송 ({basename}): {summary}")
            from websync.integrations.notifier import ToastNotifier
            ToastNotifier.show_toast("파일 부분 업로드", summary, is_error=True)
            messagebox.showwarning("부분 성공", f"일부 기기만 전송되었습니다.\n{summary}")
        else:
            self.app._log_message(f"❌ 파일 전송 실패 ({basename}): {summary}")
            from websync.integrations.notifier import ToastNotifier
            ToastNotifier.show_toast("파일 업로드 실패", "기기 전송 오류. 연결 상태 확인 요망.", is_error=True)
            messagebox.showerror("오류", "기기로 전송하지 못했습니다.")

    # ------------------------------------------------------------------
    # 스케줄러
    # ------------------------------------------------------------------
    def _register_schedule(self):
        self.app._save_ui_settings()
        h, m = self.hour_cb.get(), self.min_cb.get()
        if self.scheduler.register_daily_task(h, m):
            messagebox.showinfo("스케줄러", f"매일 {h}:{m}에 백그라운드 동기화 스케줄이 등록되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = True
            self.app._safe_save_config(config)
        else:
            messagebox.showerror("스케줄러", "스케줄러 등록에 실패했습니다. 관리자 권한을 확인하세요.")
        self._refresh_schedule_status()

    def _unregister_schedule(self):
        if self.scheduler.unregister_task():
            messagebox.showinfo("스케줄러", "스케줄 작업이 해제되었습니다.")
            config = self.service.config
            config["schedule"]["enabled"] = False
            self.app._safe_save_config(config)
        else:
            messagebox.showwarning("스케줄러", "스케줄 해제에 실패했거나 등록된 작업이 없습니다.")
        self._refresh_schedule_status()

    def _refresh_schedule_status(self):
        status = self.scheduler.get_task_status()
        self.sched_status_label.config(text=f"스케줄러 상태: {status}")

    # ------------------------------------------------------------------
    # 추가 기기 관리 팝업
    # ------------------------------------------------------------------
    def _refresh_devices_tree(self):
        for item in self.devices_tree.get_children():
            self.devices_tree.delete(item)
        for idx, dev in enumerate(self.service.config.get("x3_devices", [])):
            self.devices_tree.insert("", "end", iid=str(idx), values=(
                dev.get("name", ""), dev.get("ip", "")
            ))

    def _add_device_popup(self):
        dialog = tk.Toplevel(self.app.root)
        dialog.title("X3 기기 추가")
        dialog.configure(bg=BG_COLOR)
        setup_dialog(dialog, self.app.root, 360, 180)
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
            primary = (config.get("x3_ip") or "").strip()
            if ip == primary:
                messagebox.showwarning("중복", "기본 기기 IP와 동일합니다.", parent=dialog)
                return
            if any(d.get("ip") == ip for d in devices):
                messagebox.showwarning("중복", "이미 등록된 IP입니다.", parent=dialog)
                return
            if name == "기본 기기" or any(d.get("name") == name for d in devices):
                messagebox.showwarning("중복", "이미 사용 중인 기기 이름입니다.", parent=dialog)
                return
            devices.append({"name": name, "ip": ip})
            if not self.app._safe_save_config(config, parent=dialog, reload=True):
                return
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
        if not self.app._safe_save_config(config, reload=True):
            return
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
        if not self.app._safe_save_config(config):
            return
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
        if not self.app._safe_save_config(config):
            return
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
        dialog = tk.Toplevel(self.app.root)
        dialog.title(title)
        dialog.configure(bg=BG_COLOR)
        setup_dialog(dialog, self.app.root, 560, 540)

        content = ttk.Frame(dialog)
        content.pack(fill="both", expand=True)

        frame = create_scrollable_frame(content)
        form = ttk.Frame(frame)
        form.pack(fill="both", expand=True, padx=20, pady=20)

        ttk.Label(form, text="사이트 이름:").grid(row=0, column=0, sticky="w", pady=8)
        name_entry = ttk.Entry(form, width=40)
        name_entry.grid(row=0, column=1, sticky="w", pady=8)

        ttk.Label(form, text="타입 (유형):").grid(row=1, column=0, sticky="w", pady=8)
        # M6: naver_cafe, naver_post 추가
        type_cb = ttk.Combobox(
            form,
            values=["css", "rss", "naver", "tistory", "brunch", "youtube", "substack", "naver_cafe", "naver_post"],
            state="readonly",
            width=15
        )
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

        # 이미지 포함 / 번역 / 상세 페이지 옵션
        opt_frame = ttk.Frame(form)
        opt_frame.grid(row=6, column=0, columnspan=2, sticky="we", pady=5)
        include_img_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt_frame, text="이미지 포함", variable=include_img_var).pack(side="left", padx=5)
        fetch_detail_var = tk.BooleanVar(value=False)
        detail_cb = ttk.Checkbutton(
            opt_frame, text="상세 페이지 본문 (CSS)", variable=fetch_detail_var
        )
        detail_cb.pack(side="left", padx=5)

        ttk.Label(opt_frame, text="번역:").pack(side="left", padx=(15, 3))
        translate_cb = ttk.Combobox(opt_frame, values=["", "ko", "en", "ja", "zh-cn", "zh-tw"], width=6)
        translate_cb.pack(side="left")
        translate_cb.set("")
        ttk.Label(opt_frame, text="(빈값=번역안함)", font=("Malgun Gothic", 8), foreground=HINT_COLOR).pack(side="left", padx=3)

        def on_type_change(event=None):
            t = type_cb.get()
            state = "disabled" if t in ("rss", "naver", "tistory", "brunch", "youtube", "substack", "naver_cafe", "naver_post") else "normal"
            for w in (item_entry, title_entry, content_entry, remove_entry):
                w.config(state=state)
            detail_cb.config(state="normal" if t == "css" else "disabled")
            if t != "css":
                fetch_detail_var.set(False)

        type_cb.bind("<<ComboboxSelected>>", on_type_change)

        if site_data:
            name_entry.insert(0, site_data.get("name", ""))
            type_cb.set(site_data.get("type", "css"))
            url_entry.insert(0, site_data.get("url", ""))
            item_entry.delete(0, tk.END); item_entry.insert(0, site_data.get("item_selector", ".post-item"))
            title_elem = site_data.get("title_selector", ".post-title")
            title_entry.delete(0, tk.END); title_entry.insert(0, title_elem)
            content_entry.delete(0, tk.END); content_entry.insert(0, site_data.get("content_selector", ".post-content"))
            remove_entry.delete(0, tk.END); remove_entry.insert(0, site_data.get("remove_selectors", ""))
            limit_entry.delete(0, tk.END); limit_entry.insert(0, str(site_data.get("limit", 5)))
            include_img_var.set(site_data.get("include_images", False))
            fetch_detail_var.set(site_data.get("fetch_detail_page", False))
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
            if not (1 <= limit <= 100):
                messagebox.showerror("오류", "수집 개수는 1~100 사이여야 합니다.", parent=dialog)
                return
            config = self.service.config
            new_site = {
                "name": name, "type": type_cb.get(), "url": url, "limit": limit,
                "enabled": site_data.get("enabled", True) if site_data else True,
                "include_images": include_img_var.get(),
                "translate_to": translate_cb.get().strip(),
                "fetch_detail_page": bool(fetch_detail_var.get()) if type_cb.get() == "css" else False,
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
            if not self.app._safe_save_config(config, parent=dialog):
                return
            self._refresh_site_tree()
            dialog.destroy()

        dlg_btn_frame = ttk.Frame(dialog)
        dlg_btn_frame.pack(side="bottom", fill="x", pady=10)
        ttk.Button(dlg_btn_frame, text="저장", command=save_site).pack(side="right", padx=10)
        ttk.Button(dlg_btn_frame, text="취소", command=dialog.destroy).pack(side="right", padx=10)

    # ------------------------------------------------------------------
    # M5: Import / Export 구현부
    # ------------------------------------------------------------------
    def _export_sites_action(self):
        selected = self.tree.selection()
        # 선택된 인덱스 계산
        indices = [int(i) for i in selected] if selected else None
        
        file_path = filedialog.asksaveasfilename(
            title="사이트 설정 내보내기",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")]
        )
        if not file_path:
            return
        
        try:
            self.config_manager.export_sites(file_path, indices)
            messagebox.showinfo("완료", "선택된 사이트 설정이 성공적으로 내보내졌습니다.")
        except Exception as e:
            messagebox.showerror("오류", f"설정 내보내기 중 오류 발생: {e}")

    def _import_sites_action(self):
        file_path = filedialog.askopenfilename(
            title="사이트 설정 가져오기",
            filetypes=[("JSON", "*.json")]
        )
        if not file_path:
            return
        
        try:
            added_sites = self.config_manager.import_sites(file_path)
            if added_sites:
                self._refresh_site_tree()
                names = ", ".join([s.get("name", "") for s in added_sites])
                messagebox.showinfo("완료", f"새로운 사이트 {len(added_sites)}개가 추가되었습니다:\n{names}")
            else:
                messagebox.showinfo("완료", "가져올 새로운 사이트 설정이 없습니다. (중복 검출)")
        except Exception as e:
            messagebox.showerror("오류", f"설정 가져오기 중 오류 발생: {e}")

    # ------------------------------------------------------------------
    # H1: 프리뷰 & 선택적 동기화 구현부
    # ------------------------------------------------------------------
    def open_preview_window(self):
        """프리뷰 실행 후 결과를 새 윈도우에 체크박스와 함께 표시합니다."""
        self.app._log_message("\n🔍 프리뷰 스크래핑을 실행합니다...")
        self.app._set_sync_ui_busy(True)
        self.app.bottom_bar.progress_bar["value"] = 0

        def run():
            log_cb = self.app._make_log_callback()
            prog_cb = self.app._make_progress_callback()
            self._preview_data = self.service.preview_articles(log_callback=log_cb, progress_callback=prog_cb)
            
            self.master.after(0, self._show_preview_results)

        threading.Thread(target=run, daemon=True).start()

    def _show_preview_results(self):
        self.app._set_sync_ui_busy(False)
        self.app.bottom_bar.progress_bar["value"] = 0
        self.app._log_message("🔍 프리뷰 스크래핑이 완료되었습니다.\n")

        if not self._preview_data:
            messagebox.showinfo("프리뷰 결과", "수집된 새로운 기사가 없습니다.")
            return

        dialog = tk.Toplevel(self.app.root)
        dialog.title("기사 프리뷰 및 선택 전송")
        dialog.geometry("700x500")
        setup_dialog(dialog, self.app.root, 700, 500)

        # 안내
        lbl = ttk.Label(dialog, text="수집된 신규 기사 중 전송할 기사를 선택한 뒤 아래 버튼을 누르세요.")
        lbl.pack(fill="x", padx=15, pady=10)

        # 테이블
        columns = ("selected", "site", "title", "url")
        tree = create_scrolled_tree(dialog, columns, height=12)
        tree.heading("selected", text="선택")
        tree.heading("site", text="사이트")
        tree.heading("title", text="기사 제목")
        tree.heading("url", text="URL")
        
        tree.column("selected", width=50, anchor="center")
        tree.column("site", width=120, anchor="w")
        tree.column("title", width=320, anchor="w")
        tree.column("url", width=180, anchor="w")

        # 체크 상태 저장
        checked_state = {i: True for i in range(len(self._preview_data))}

        def refresh_tree():
            for item in tree.get_children():
                tree.delete(item)
            for idx, art in enumerate(self._preview_data):
                chk = "☑" if checked_state[idx] else "☐"
                tree.insert("", "end", iid=str(idx), values=(
                    chk, art["site_name"], art["title"], art["url"]
                ))

        refresh_tree()

        # 체크 클릭 핸들링
        def on_click(event):
            item = tree.identify_row(event.y)
            if not item:
                return
            idx = int(item)
            checked_state[idx] = not checked_state[idx]
            refresh_tree()

        tree.bind("<Button-1>", on_click)

        # 전체 토글
        def toggle_all():
            val = not all(checked_state.values())
            for k in checked_state:
                checked_state[k] = val
            refresh_tree()

        # 동기화 실행
        def run_selected_sync():
            selected_arts = [self._preview_data[i] for i, checked in checked_state.items() if checked]
            if not selected_arts:
                messagebox.showwarning("선택 누락", "전송할 기사를 최소 하나 이상 선택해 주세요.", parent=dialog)
                return
            
            dialog.destroy()
            self._run_selected_sync_task(selected_arts)

        btn_bar = ttk.Frame(dialog)
        btn_bar.pack(fill="x", side="bottom", pady=10, padx=15)
        
        ttk.Button(btn_bar, text="전체 선택/해제", command=toggle_all).pack(side="left")
        ttk.Button(btn_bar, text="취소", command=dialog.destroy).pack(side="right", padx=5)
        ttk.Button(btn_bar, text="★ 선택 기사 기기로 전송", command=run_selected_sync).pack(side="right")

    def _run_selected_sync_task(self, selected_articles):
        if self.service.is_pipeline_running():
            messagebox.showwarning("실행 제한", "현재 다른 동기화 작업이 실행 중입니다. 완료 후 다시 시도해 주세요.")
            return

        self.app._set_sync_ui_busy(True)
        self.app.bottom_bar.progress_bar["value"] = 0
        self.app._log_message(f"\n=== 선택 기사 {len(selected_articles)}건 동기화 실행 ===")

        def task():
            log_cb = self.app._make_log_callback()
            prog_cb = self.app._make_progress_callback()
            self.service.sync_selected_articles(selected_articles, log_callback=log_cb, progress_callback=prog_cb)
            self.master.after(0, self.app._sync_finished_ui)

        threading.Thread(target=task, daemon=True).start()

