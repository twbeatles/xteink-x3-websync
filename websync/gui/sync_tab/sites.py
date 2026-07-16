from __future__ import annotations

import os
import sys
import hashlib
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from websync.gui.widgets import (
    BG_COLOR, TEXT_BG, SECONDARY_BG, HINT_COLOR, YELLOW_COLOR, GREEN_COLOR, RED_COLOR,
    create_scrollable_frame, create_scrolled_tree, setup_dialog, bind_widget_mousewheel
)
from websync.upload.uploader import X3Uploader, normalize_device_host
from websync.config.exceptions import ConfigSaveError, ConfigLoadError


class SyncSitesMixin:
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
            values=["css", "rss", "naver", "tistory", "brunch", "youtube", "substack", "naver_cafe", "naver_post", "soonsal", "moneyletter"],
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
            state = "disabled" if t in ("rss", "naver", "tistory", "brunch", "youtube", "substack", "naver_cafe", "naver_post", "soonsal", "moneyletter") else "normal"
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
                # import_sites는 파일에 저장하지만 self.service.config(메모리)는 갱신하지 않으므로
                # 명시적으로 config를 리로드하여 _refresh_site_tree가 최신 사이트를 반영하도록 함
                self.service._reload_config()
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

