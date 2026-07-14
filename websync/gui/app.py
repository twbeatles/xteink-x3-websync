"""Tkinter 기반의 메인 GUI 매니저"""
import os
import hashlib
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, messagebox

from websync.integrations.calibre import CalibreManager
from websync.core.paths import resolve_path
from websync.upload.uploader import X3Uploader
from websync.scheduler.manager import SchedulerManager
from websync.integrations.notifier import ToastNotifier
from websync.pipeline.service import SyncService
from websync.core.logger import get_log_dir
from websync.config.exceptions import ConfigSaveError

# 분리된 탭 및 바 컴포넌트 임포트
from websync.gui.widgets import (
    BG_COLOR, FG_COLOR, ACCENT_COLOR, SECONDARY_BG, TEXT_BG, GREEN_COLOR, RED_COLOR, YELLOW_COLOR, HINT_COLOR,
    center_window, setup_dialog
)
from websync.gui.tab_sync import SyncTab
from websync.gui.tab_calibre import CalibreTab
from websync.gui.tab_history import HistoryTab
from websync.gui.tab_settings import SettingsTab
from websync.gui.bottom_bar import BottomBar


class SyncAppGui:
    """Tkinter 탭형 인터페이스 및 동기화 비즈니스 중개 GUI 컨트롤러"""

    def __init__(self, service: SyncService):
        self.service = service
        self.scheduler = SchedulerManager()
        self.calibre = CalibreManager(
            self.service.config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"),
            self.service.config.get("calibre_library_path", ""),
        )

        # 서버 인스턴스
        self._opds_server = None
        self._web_dashboard = None
        self._calibre_watcher = None

        self.root = tk.Tk()
        self.root.title("Xteink X3 WebSync Manager")
        self.root.geometry("860x760")
        self.root.minsize(640, 480)
        self.root.resizable(True, True)

        self._sync_busy = False

        self._setup_styles()
        self._build_ui()
        self._load_config_to_ui()
        
        self.root.after(0, lambda: center_window(self.root, 860, 760))
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)

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
        self.tab_settings = SettingsTab(self.notebook, self)

        self.notebook.add(self.tab_sync, text=" 뉴스 동기화 ")
        self.notebook.add(self.tab_calibre, text=" Calibre 서재 ")
        self.notebook.add(self.tab_history, text=" 📋 동기화 이력 ")
        self.notebook.add(self.tab_settings, text=" ⚙️ 고급 & 서버 설정 ")

        # 하단 바
        bottom_container = ttk.Frame(self.main_paned)
        self.main_paned.add(bottom_container, weight=1)
        self.bottom_bar = BottomBar(bottom_container, self)

    def _bind_autosave(self, widget: tk.Misc) -> None:
        widget.bind("<FocusOut>", lambda _e: self._save_ui_settings())

    def _set_sync_ui_busy(self, busy: bool) -> None:
        self._sync_busy = busy
        state = "disabled" if busy else "normal"
        
        # 각 탭의 활성 버튼 상태 제어
        self.bottom_bar.sync_now_btn.config(state=state)
        self.bottom_bar.preview_btn.config(state=state)
        self.tab_sync.direct_upload_btn.config(state=state)
        self.tab_sync.test_conn_btn.config(state=state)
        self.tab_calibre.calibre_send_btn.config(state=state)
        self.tab_calibre.calibre_conn_btn.config(state=state)

    def _log_message(self, message: str):
        self.bottom_bar.log_txt.config(state="normal")
        self.bottom_bar.log_txt.insert(tk.END, message + "\n")
        self.bottom_bar.log_txt.see(tk.END)
        self.bottom_bar.log_txt.config(state="disabled")

    def _update_progress(self, current: int, total: int):
        if total > 0:
            self.bottom_bar.progress_bar["maximum"] = total
            self.bottom_bar.progress_bar["value"] = current
        else:
            self.bottom_bar.progress_bar["value"] = 0

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
        config = self.service.config
        return X3Uploader(
            config.get("x3_ip", "").strip() or self.tab_sync.ip_entry.get().strip(),
            config.get("x3_devices", []),
        )

    def _ip_display_name(self, ip: str) -> str:
        for d in self._make_uploader()._build_target_list():
            if d["ip"] == ip:
                return d.get("name") or ip
        return ip

    def _summarize_upload_results(self, results: dict) -> tuple[bool, bool, str]:
        if not results:
            return False, False, "등록된 기기 없음"
        ok_labels = [f"{self._ip_display_name(ip)}({ip})" for ip, ok in results.items() if ok]
        fail_labels = [f"{self._ip_display_name(ip)}({ip})" for ip, ok in results.items() if not ok]
        parts = []
        if ok_labels:
            parts.append(f"성공: {', '.join(ok_labels)}")
        if fail_labels:
            parts.append(f"실패: {', '.join(fail_labels)}")
        return all(results.values()), bool(ok_labels), " | ".join(parts)

    def _safe_save_config(self, config: dict, *, parent=None, reload: bool = False) -> bool:
        try:
            self.service.config_manager.save_config(config)
            if reload:
                self.service._reload_config()
            return True
        except ConfigSaveError as e:
            messagebox.showerror("설정 저장 실패", str(e), parent=parent)
            self._log_message(f"❌ 설정 저장 실패: {e}")
            return False
        except Exception as e:
            messagebox.showerror("설정 저장 실패", str(e), parent=parent)
            self._log_message(f"❌ 설정 저장 실패: {e}")
            return False

    def _get_log_for_web(self) -> str:
        try:
            content = self.bottom_bar.log_txt.get("1.0", "end-1c")
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
    # 설정 동기화 및 윈도우 컨트롤
    # ------------------------------------------------------------------
    def _load_config_to_ui(self):
        config = self.service.config
        
        # 1. SyncTab 설정 로드
        self.tab_sync.ip_entry.insert(0, config.get("x3_ip", "crosspoint.local"))
        self.tab_sync.dir_entry.insert(0, config.get("output_dir", "./output"))
        self.tab_sync.font_cb.set(config.get("font_family", "serif"))
        self.tab_sync.font_size_sp.set(str(config.get("font_size", 16)))
        self.tab_sync.line_height_sp.set(str(config.get("line_height", 1.7)))
        self.tab_sync.cover_var.set(config.get("epub_cover", True))

        sched_conf = config.get("schedule", {})
        self.tab_sync.hour_cb.set(sched_conf.get("hour", "07"))
        self.tab_sync.min_cb.set(sched_conf.get("minute", "00"))
        
        self.tab_sync._refresh_devices_tree()
        self.tab_sync._refresh_site_tree()
        self.tab_sync._refresh_schedule_status()

        # 2. CalibreTab 설정 로드
        self.tab_calibre.calibre_entry.insert(0, config.get("calibre_path", "C:\\Program Files\\Calibre2\\calibredb.exe"))
        self.tab_calibre.calibre_lib_entry.insert(0, config.get("calibre_library_path", ""))
        threading.Thread(target=self.tab_calibre._test_and_load_calibre, kwargs={"silent": True}, daemon=True).start()

        # 3. HistoryTab 로드
        self.tab_history._refresh_history()

        # 4. SettingsTab 설정 로드
        # M4 & M7 설정 로드
        self.tab_settings.merge_mode_var.set(config.get("epub_merge_mode", "per_site"))
        self.tab_settings.epub_theme_cb.set(config.get("epub_theme", "default"))
        self.tab_settings.custom_css_entry.insert(0, config.get("epub_custom_css", ""))
        self.tab_settings._on_theme_changed()

        opds_conf = config.get("opds_server", {})
        self.tab_settings.opds_port_sp.set(str(opds_conf.get("port", 8765)))
        self.tab_settings.opds_allow_lan_var.set(opds_conf.get("allow_lan", False))
        opds_key = opds_conf.get("api_key", "")
        self.tab_settings.opds_api_key_label.config(
            text=f"OPDS API 키: {opds_key[:8]}... (config.json, LAN 시 X-Api-Key 헤더)" if opds_key else ""
        )

        web_conf = config.get("web_dashboard", {})
        self.tab_settings.web_port_sp.set(str(web_conf.get("port", 8766)))
        self.tab_settings.web_allow_lan_var.set(web_conf.get("allow_lan", False))
        token = web_conf.get("api_token", "")
        self.tab_settings.web_token_label.config(text=f"API 토큰: {token[:8]}... (config.json)" if token else "")

        watch_conf = config.get("calibre_watch", {})
        self.tab_settings.watch_dir_entry.insert(0, watch_conf.get("watch_dir", ""))

        ai_conf = config.get("ai_summary", {})
        self.tab_settings.ai_enabled_var.set(ai_conf.get("enabled", False))
        self.tab_settings.ai_provider_cb.set(ai_conf.get("provider", "openai"))
        self.tab_settings.ai_key_entry.insert(0, ai_conf.get("api_key", ""))

        trans_conf = config.get("translation", {})
        self.tab_settings.trans_enabled_var.set(trans_conf.get("enabled", False))
        self.tab_settings.trans_provider_cb.set(trans_conf.get("provider", "googletrans"))

    def _save_ui_settings(self):
        config = self.service.config
        
        # 1. SyncTab에서 정보 가져옴
        config["x3_ip"] = self.tab_sync.ip_entry.get().strip()
        config["output_dir"] = self.tab_sync.dir_entry.get().strip()
        config["font_family"] = self.tab_sync.font_cb.get()
        config["epub_cover"] = self.tab_sync.cover_var.get()
        try:
            config["font_size"] = int(self.tab_sync.font_size_sp.get())
        except ValueError:
            config["font_size"] = 16
        try:
            config["line_height"] = float(self.tab_sync.line_height_sp.get())
        except ValueError:
            config["line_height"] = 1.7
        
        config.setdefault("schedule", {})
        config["schedule"]["hour"] = self.tab_sync.hour_cb.get()
        config["schedule"]["minute"] = self.tab_sync.min_cb.get()

        # 2. CalibreTab에서 정보 가져옴
        config["calibre_path"] = self.tab_calibre.calibre_entry.get().strip()
        config["calibre_library_path"] = self.tab_calibre.calibre_lib_entry.get().strip()

        # 3. SettingsTab에서 정보 가져옴
        # M4 & M7 가져옴
        config["epub_merge_mode"] = self.tab_settings.merge_mode_var.get()
        config["epub_theme"] = self.tab_settings.epub_theme_cb.get()
        config["epub_custom_css"] = self.tab_settings.custom_css_entry.get().strip()

        try:
            config.setdefault("opds_server", {})["port"] = int(self.tab_settings.opds_port_sp.get())
            config["opds_server"]["allow_lan"] = self.tab_settings.opds_allow_lan_var.get()
        except ValueError:
            pass
        try:
            config.setdefault("web_dashboard", {})["port"] = int(self.tab_settings.web_port_sp.get())
            config["web_dashboard"]["allow_lan"] = self.tab_settings.web_allow_lan_var.get()
        except ValueError:
            pass
        
        config.setdefault("calibre_watch", {})["watch_dir"] = self.tab_settings.watch_dir_entry.get().strip()

        # 저장 실행
        if not self._safe_save_config(config, reload=True):
            return
        
        self.calibre.calibre_path = config["calibre_path"]
        self.calibre.library_path = config["calibre_library_path"]

    # ------------------------------------------------------------------
    # 즉시 동기화 실행
    # ------------------------------------------------------------------
    def _run_immediate_sync(self):
        self._save_ui_settings()
        self._set_sync_ui_busy(True)
        self.bottom_bar.progress_bar["value"] = 0
        self._log_message("\n=== 동기화 실행 요청 받음 ===")

        def run():
            self.service.run_sync_pipeline(
                log_callback=self._make_log_callback(),
                progress_callback=self._make_progress_callback(),
            )
            self.root.after(0, self._sync_finished_ui)

        threading.Thread(target=run, daemon=True).start()

    def _sync_finished_ui(self):
        maximum = float(self.bottom_bar.progress_bar["maximum"] or 0)
        if maximum > 0:
            self.bottom_bar.progress_bar["value"] = maximum
            self.root.after(1500, lambda: self.bottom_bar.progress_bar.configure(value=0))
        else:
            self.bottom_bar.progress_bar["value"] = 0
        self._set_sync_ui_busy(False)
        self._log_message("=== 동기화 프로세스 종료 ===\n")
        self.tab_history._refresh_history()

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
