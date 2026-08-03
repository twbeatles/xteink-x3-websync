"""사이트 등록 다이얼로그용 CSS 선택자 도우미 패널.

순수 로직은 websync.scrapers.selector_assistant 에 두고,
이 모듈은 Treeview·버튼·스레드 콜백만 담당한다.

스레드 규약:
- 네트워크 작업만 daemon 스레드에서 수행
- self._html / _analysis / 위젯 갱신은 메인 스레드(after 콜백)에서만
- 다이얼로그 파괴 시 after 콜백은 no-op, _busy 는 항상 해제
"""
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import ttk, messagebox
from typing import Any, Callable, Optional

from websync.gui.widgets import HINT_COLOR, GREEN_COLOR
from websync.scrapers.selector_assistant import (
    PageAnalysis,
    analyze_page,
    parse_html,
    evaluate_selector,
    is_private_or_local_url,
)


# 선택자 필드 역할 키
ROLE_ITEM = "item"
ROLE_TITLE = "title"
ROLE_LINK = "link"
ROLE_CONTENT = "content"
ROLE_REMOVE = "remove"

ROLE_LABELS = {
    ROLE_ITEM: "아이템",
    ROLE_TITLE: "제목",
    ROLE_LINK: "링크",
    ROLE_CONTENT: "본문",
    ROLE_REMOVE: "제거",
}


class SelectorWizardPanel:
    """CSS 선택자 분석/테스트/DOM 픽 패널."""

    def __init__(
        self,
        parent: tk.Misc,
        dialog: tk.Toplevel,
        *,
        get_url: Callable[[], str],
        get_entries: Callable[[], dict[str, Any]],
        set_entry: Callable[[str, str], None],
        set_type: Callable[[str], None],
        set_url: Callable[[str], None],
        get_site_snapshot: Callable[[], dict],
        on_type_change: Optional[Callable[[], None]] = None,
        apply_site_config: Optional[Callable[[dict], None]] = None,
        is_pipeline_running: Optional[Callable[[], bool]] = None,
    ):
        self.parent = parent
        self.dialog = dialog
        self.get_url = get_url
        self.get_entries = get_entries
        self.set_entry = set_entry
        self.set_type = set_type
        self.set_url = set_url
        self.get_site_snapshot = get_site_snapshot
        self.on_type_change = on_type_change
        self.apply_site_config = apply_site_config
        self.is_pipeline_running = is_pipeline_running

        self._html: str = ""
        self._base_url: str = ""
        self._busy = False
        self._req_gen = 0  # stale after 콜백 폐기용
        self._analysis: Optional[PageAnalysis] = None
        self._outline_iid_to_path: dict[str, str] = {}

        self.role_var = tk.StringVar(value=ROLE_ITEM)

        self.frame = ttk.LabelFrame(parent, text=" 선택자 도우미 (CSS) ")
        self._build()

    # ------------------------------------------------------------------
    # 스레드/다이얼로그 안전 헬퍼
    # ------------------------------------------------------------------

    def _dialog_alive(self) -> bool:
        try:
            return bool(self.dialog.winfo_exists())
        except tk.TclError:
            return False

    def _ui_call(self, gen: int, fn: Callable[[], None]) -> None:
        """메인 스레드에서만 호출. 파괴·stale 요청이면 _busy 만 정리."""
        if gen != self._req_gen:
            return
        if not self._dialog_alive():
            self._busy = False
            return
        try:
            fn()
        except tk.TclError:
            self._busy = False
        except Exception:
            self._busy = False
            raise

    def _schedule(self, gen: int, fn: Callable[[], None]) -> None:
        """워커 → 메인 스레드 스케줄. 다이얼로그가 없으면 no-op."""
        def _run():
            self._ui_call(gen, fn)

        if not self._dialog_alive():
            # 이미 닫힘 — gen 무효화는 메인에서 busy 정리
            try:
                self.dialog.after(0, lambda: self._ui_call(gen, lambda: None))
            except tk.TclError:
                self._busy = False
            return
        try:
            self.dialog.after(0, _run)
        except tk.TclError:
            self._busy = False

    def _begin_work(self, status: str) -> Optional[int]:
        if self._busy:
            return None
        if not self._dialog_alive():
            return None
        self._busy = True
        self._req_gen += 1
        gen = self._req_gen
        try:
            self._set_status(status)
        except tk.TclError:
            self._busy = False
            return None
        return gen

    def pack(self, **kwargs) -> None:
        self.frame.pack(**kwargs)

    def grid(self, **kwargs) -> None:
        self.frame.grid(**kwargs)

    def set_css_widgets_state(self, enabled: bool) -> None:
        # 비CSS일 때도 분석(RSS/전용 제안)은 유용하므로 패널은 유지
        pass

    def _set_status(self, msg: str, *, ok: bool = False) -> None:
        if not self._dialog_alive():
            return
        try:
            self.status_label.configure(
                text=msg,
                foreground=GREEN_COLOR if ok else HINT_COLOR,
            )
        except tk.TclError:
            pass

    def _set_result(self, text: str) -> None:
        if not self._dialog_alive():
            return
        try:
            self.result_text.configure(state="normal")
            self.result_text.delete("1.0", tk.END)
            self.result_text.insert(tk.END, text)
            self.result_text.configure(state="disabled")
        except tk.TclError:
            pass

    def _clear_hint_buttons(self) -> None:
        if not self._dialog_alive():
            return
        try:
            for w in self.hint_frame.winfo_children():
                w.destroy()
        except tk.TclError:
            pass

    def _build(self) -> None:
        top = ttk.Frame(self.frame)
        top.pack(fill="x", padx=8, pady=6)

        ttk.Button(top, text="페이지 분석", command=self._on_analyze).pack(side="left", padx=2)
        ttk.Button(top, text="선택자 테스트", command=self._on_test).pack(side="left", padx=2)
        ttk.Button(top, text="수집 미리보기", command=self._on_preview_scrape).pack(side="left", padx=2)
        ttk.Button(top, text="추천 적용", command=self._on_apply_suggestions).pack(side="left", padx=2)
        ttk.Button(top, text="최적 설정 적용", command=self._on_apply_recommended).pack(side="left", padx=2)

        self.status_label = ttk.Label(
            self.frame,
            text="URL 입력 후 「페이지 분석」으로 선택자를 찾거나 검증하세요.",
            font=("Malgun Gothic", 10),
            foreground=HINT_COLOR,
            wraplength=520,
            justify="left",
        )
        self.status_label.pack(fill="x", padx=10, pady=(0, 4))

        role_row = ttk.Frame(self.frame)
        role_row.pack(fill="x", padx=8, pady=2)
        ttk.Label(role_row, text="트리 클릭 시 채울 필드:").pack(side="left")
        for key, label in ROLE_LABELS.items():
            ttk.Radiobutton(
                role_row, text=label, value=key, variable=self.role_var
            ).pack(side="left", padx=3)

        self.hint_frame = ttk.Frame(self.frame)
        self.hint_frame.pack(fill="x", padx=8, pady=2)

        paned = ttk.Panedwindow(self.frame, orient=tk.HORIZONTAL)
        paned.pack(fill="both", expand=True, padx=8, pady=4)

        left = ttk.Frame(paned)
        right = ttk.Frame(paned)
        paned.add(left, weight=3)
        paned.add(right, weight=2)

        ttk.Label(left, text="DOM 구조 (클릭 → 선택자 삽입)").pack(anchor="w")
        tree_wrap = ttk.Frame(left)
        tree_wrap.pack(fill="both", expand=True)
        self.dom_tree = ttk.Treeview(tree_wrap, show="tree", height=10, selectmode="browse")
        ys = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.dom_tree.yview)
        self.dom_tree.configure(yscrollcommand=ys.set)
        self.dom_tree.pack(side="left", fill="both", expand=True)
        ys.pack(side="right", fill="y")
        self.dom_tree.bind("<<TreeviewSelect>>", self._on_dom_select)

        ttk.Label(right, text="테스트 / 미리보기 결과").pack(anchor="w")
        self.result_text = tk.Text(right, height=10, width=36, wrap="word", font=("Consolas", 9))
        rsb = ttk.Scrollbar(right, orient="vertical", command=self.result_text.yview)
        self.result_text.configure(yscrollcommand=rsb.set)
        self.result_text.pack(side="left", fill="both", expand=True)
        rsb.pack(side="right", fill="y")
        self.result_text.configure(state="disabled")

    def _warn_private_url(self, url: str) -> bool:
        """사설/로컬 URL이면 사용자 확인. 진행하면 True."""
        if not is_private_or_local_url(url):
            return True
        return bool(
            messagebox.askyesno(
                "내부 주소 확인",
                "입력한 URL이 로컬 또는 사설 네트워크 주소로 보입니다.\n"
                "계속하면 해당 호스트로 HTTP 요청을 보냅니다.\n\n계속할까요?",
                parent=self.dialog,
            )
        )

    def _on_analyze(self) -> None:
        url = self.get_url().strip()
        if not url:
            messagebox.showwarning("경고", "수집 주소를 입력해 주세요.", parent=self.dialog)
            return
        if not (url.startswith("http://") or url.startswith("https://")):
            messagebox.showerror("오류", "URL은 http:// 또는 https://로 시작해야 합니다.", parent=self.dialog)
            return
        if not self._warn_private_url(url):
            return
        gen = self._begin_work("페이지 불러오는 중… (피드 확인 포함, 수 초 소요될 수 있음)")
        if gen is None:
            return
        try:
            self._set_result("")
        except tk.TclError:
            self._busy = False
            return

        def work():
            try:
                analysis = analyze_page(url)
            except Exception as e:
                analysis = PageAnalysis(url=url, base_url=url, error=f"분석 예외: {e}")
            self._schedule(gen, lambda: self._apply_analysis(analysis, gen))

        threading.Thread(target=work, daemon=True).start()

    def _apply_analysis(self, analysis: PageAnalysis, gen: int) -> None:
        if gen != self._req_gen:
            return
        self._busy = False
        if not self._dialog_alive():
            return

        self._analysis = analysis
        self._html = analysis.html or ""
        self._base_url = analysis.base_url or analysis.url

        if analysis.error:
            self._set_status(analysis.error)
            self._set_result(analysis.error)
            return

        try:
            self.dom_tree.delete(*self.dom_tree.get_children())
        except tk.TclError:
            return
        self._outline_iid_to_path.clear()
        iid_map: dict[int, str] = {}
        for node in analysis.outline:
            parent = "" if node.parent_index < 0 else iid_map.get(node.parent_index, "")
            try:
                iid = self.dom_tree.insert(parent, "end", text=node.label)
            except tk.TclError:
                return
            iid_map[node.index] = iid
            self._outline_iid_to_path[iid] = node.css_path

        self._clear_hint_buttons()
        if analysis.platform:
            p = analysis.platform
            ttk.Button(
                self.hint_frame,
                text=f"전용 타입 권장: {p} (전환)",
                command=lambda pt=p: self._switch_platform(pt),
            ).pack(side="left", padx=2, pady=2)
        for feed in analysis.feeds[:3]:
            label = feed.url if len(feed.url) <= 52 else feed.url[:50] + "…"
            ttk.Button(
                self.hint_frame,
                text=f"RSS 권장: {label}",
                command=lambda f=feed: self._switch_rss(f.url),
            ).pack(side="left", padx=2, pady=2)
        if analysis.recommended_site:
            ttk.Button(
                self.hint_frame,
                text="최적 설정 적용",
                command=self._on_apply_recommended,
            ).pack(side="left", padx=2, pady=2)

        lines = [
            f"제목: {analysis.title or '(없음)'}",
            f"URL: {analysis.base_url}",
            f"권장 모드: {analysis.recommend_mode}",
        ]
        for note in (analysis.notes or [])[:6]:
            lines.append(f"· {note}")
        if analysis.platform:
            lines.append(f"플랫폼 감지: {analysis.platform} → 전용 스크래퍼 권장")
        if analysis.feeds:
            lines.append(f"RSS/Atom {len(analysis.feeds)}개 발견")
            for f in analysis.feeds[:3]:
                lines.append(f"  - {f.url}")
        sug = analysis.suggestions or {}
        for role, key in (("아이템", "item"), ("제목", "title"), ("링크", "link"), ("본문", "content")):
            items = sug.get(key) or []
            if items:
                top = items[0]
                lines.append(
                    f"추천 {role}: {top.get('selector')} "
                    f"(점수 {top.get('score')}, {top.get('count')}건) — {top.get('sample', '')[:40]}"
                )
        if analysis.fetch_detail_recommended:
            lines.append("상세 페이지 본문 옵션 권장: ON")
        rec = analysis.recommended_site or {}
        if rec:
            lines.append(
                f"\n[최적 설정] type={rec.get('type')} "
                f"fetch_detail={rec.get('fetch_detail_page')} "
                f"— {rec.get('_recommend_note', '')}"
            )
        self._set_result("\n".join(lines))
        self._set_status(
            "분석 완료. 「최적 설정 적용」 또는 「추천 적용」·DOM 클릭으로 선택자를 채우세요.",
            ok=True,
        )

    def _switch_platform(self, platform: str) -> None:
        self.set_type(platform)
        if self.on_type_change:
            self.on_type_change()
        self._set_status(f"타입을 '{platform}'(으)로 전환했습니다. 선택자는 전용 스크래퍼가 처리합니다.", ok=True)

    def _switch_rss(self, feed_url: str) -> None:
        self.set_type("rss")
        self.set_url(feed_url)
        if self.on_type_change:
            self.on_type_change()
        self._set_status("RSS 피드로 전환했습니다. 선택자 없이 수집할 수 있습니다.", ok=True)

    def _on_dom_select(self, _event=None) -> None:
        sel = self.dom_tree.selection()
        if not sel:
            return
        path = self._outline_iid_to_path.get(sel[0], "")
        if not path:
            return
        role = self.role_var.get()
        self.set_entry(role, path)
        self._set_status(f"{ROLE_LABELS.get(role, role)} 필드에 선택자 삽입: {path}", ok=True)

    def _on_apply_suggestions(self) -> None:
        if not self._analysis or not self._analysis.suggestions:
            messagebox.showinfo(
                "안내",
                "먼저 「페이지 분석」을 실행해 주세요.",
                parent=self.dialog,
            )
            return
        if self._analysis.recommend_mode in ("rss", "platform"):
            if not messagebox.askyesno(
                "확인",
                f"이 페이지는 '{self._analysis.recommend_mode}' 모드가 더 안정적입니다.\n"
                "그래도 CSS 선택자 추천만 적용할까요?\n"
                "(「최적 설정 적용」을 쓰면 권장 모드로 채웁니다.)",
                parent=self.dialog,
            ):
                return
        sug = self._analysis.suggestions
        applied = []
        mapping = [
            (ROLE_ITEM, "item"),
            (ROLE_TITLE, "title"),
            (ROLE_LINK, "link"),
            (ROLE_CONTENT, "content"),
        ]
        for role, key in mapping:
            items = sug.get(key) or []
            if items:
                sel = items[0].get("selector") or ""
                if sel == ".":
                    sel = "a" if role == ROLE_TITLE else ("a[href]" if role == ROLE_LINK else sel)
                if sel and sel != ".":
                    self.set_entry(role, sel)
                    applied.append(f"{ROLE_LABELS[role]}={sel}")
        if self.apply_site_config and self._analysis.fetch_detail_recommended:
            self.apply_site_config({"fetch_detail_page": True, "type": "css"})
            applied.append("상세본문=ON")
        if applied:
            self._set_status("추천 선택자 적용: " + ", ".join(applied), ok=True)
        else:
            self._set_status("추천 후보를 찾지 못했습니다. DOM 트리에서 직접 골라 주세요.")

    def _on_apply_recommended(self) -> None:
        if not self._analysis or not self._analysis.recommended_site:
            messagebox.showinfo(
                "안내",
                "먼저 「페이지 분석」을 실행해 주세요.",
                parent=self.dialog,
            )
            return
        rec = dict(self._analysis.recommended_site)
        note = rec.pop("_recommend_note", "") or ""
        rec.pop("_notes", None)
        if self.apply_site_config:
            self.apply_site_config(rec)
        else:
            self.set_type(rec.get("type") or "css")
            if rec.get("url"):
                self.set_url(rec["url"])
            if (rec.get("type") or "") == "css":
                for role, key in (
                    (ROLE_ITEM, "item_selector"),
                    (ROLE_TITLE, "title_selector"),
                    (ROLE_LINK, "link_selector"),
                    (ROLE_CONTENT, "content_selector"),
                    (ROLE_REMOVE, "remove_selectors"),
                ):
                    if rec.get(key):
                        self.set_entry(role, rec[key])
            if self.on_type_change:
                self.on_type_change()
        self._set_status(f"최적 설정 적용 완료. {note}", ok=True)
        lines = [
            "최적 설정 적용됨",
            f"type={rec.get('type')}",
            f"url={rec.get('url', '')}",
            f"item={rec.get('item_selector', '-')}",
            f"title={rec.get('title_selector', '-')}",
            f"link={rec.get('link_selector', '-')}",
            f"content={rec.get('content_selector', '-')}",
            f"fetch_detail={rec.get('fetch_detail_page')}",
            note,
        ]
        self._set_result("\n".join(lines))

    def _run_selector_test(self, html: str, base: str, entries: dict, field: str, selector: str) -> str:
        soup = parse_html(html, base)
        if field in ("title", "link") and (entries.get("item") or "").strip():
            item_sel = entries["item"].strip()
            try:
                items = soup.select(item_sel)
            except Exception as e:
                return f"아이템 선택자 오류: {e}"
            if not items:
                return f"아이템 '{item_sel}' 매칭 0건 — 아이템 선택자를 먼저 확인하세요."
            lines = [f"아이템 {len(items)}건 기준, 상대 선택자 '{selector}':"]
            hit = 0
            for i, it in enumerate(items[:8]):
                r = evaluate_selector(soup, selector, limit=1, root=it)
                if r.error:
                    lines.append(f"  [{i+1}] 오류: {r.error}")
                elif r.count:
                    hit += 1
                    sample = r.samples[0].text if r.samples else ""
                    lines.append(f"  [{i+1}] OK — {sample}")
                else:
                    lines.append(f"  [{i+1}] 없음")
            lines.append(f"요약: 상위 {min(8, len(items))}개 중 {hit}개 매칭")
            return "\n".join(lines)
        r = evaluate_selector(soup, selector, limit=8)
        if r.error:
            return r.error
        lines = [f"선택자: {selector}", f"매칭: {r.count}건"]
        for i, s in enumerate(r.samples, 1):
            lines.append(f"  {i}. {s.text}")
        return "\n".join(lines)

    def _on_test(self) -> None:
        entries = self.get_entries()
        role = self.role_var.get()
        key_map = {
            ROLE_ITEM: "item",
            ROLE_TITLE: "title",
            ROLE_LINK: "link",
            ROLE_CONTENT: "content",
            ROLE_REMOVE: "remove",
        }
        field = key_map.get(role, "item")
        selector = (entries.get(field) or "").strip()
        if not selector:
            messagebox.showwarning("경고", "테스트할 선택자가 비어 있습니다.", parent=self.dialog)
            return

        if self._html:
            msg = self._run_selector_test(self._html, self._base_url, entries, field, selector)
            self._set_result(msg)
            self._set_status("선택자 테스트 완료 (캐시 HTML).", ok=True)
            return

        url = self.get_url().strip()
        if not url:
            messagebox.showwarning("경고", "URL이 필요합니다.", parent=self.dialog)
            return
        if not self._warn_private_url(url):
            return
        gen = self._begin_work("페이지 로드 후 테스트 중…")
        if gen is None:
            return

        def work():
            analysis: Optional[PageAnalysis] = None
            try:
                analysis = analyze_page(url)
                if analysis.error:
                    msg = analysis.error
                else:
                    msg = self._run_selector_test(
                        analysis.html, analysis.base_url, entries, field, selector
                    )
            except Exception as e:
                msg = f"테스트 실패: {e}"
            # 상태 갱신은 메인 스레드에서만
            self._schedule(
                gen,
                lambda: self._finish_test(msg, analysis, gen),
            )

        threading.Thread(target=work, daemon=True).start()

    def _finish_test(
        self,
        msg: str,
        analysis: Optional[PageAnalysis],
        gen: int,
    ) -> None:
        if gen != self._req_gen:
            return
        self._busy = False
        if not self._dialog_alive():
            return
        if analysis is not None and not analysis.error:
            self._html = analysis.html or ""
            self._base_url = analysis.base_url or analysis.url
            self._analysis = analysis
        self._set_result(msg)
        self._set_status("선택자 테스트 완료.", ok=True)

    def _on_preview_scrape(self) -> None:
        snap = self.get_site_snapshot()
        if (snap.get("type") or "css") != "css":
            messagebox.showinfo(
                "안내",
                "수집 미리보기는 CSS 타입에서만 지원합니다.",
                parent=self.dialog,
            )
            return
        if not snap.get("url"):
            messagebox.showwarning("경고", "수집 주소를 입력해 주세요.", parent=self.dialog)
            return
        if self.is_pipeline_running and self.is_pipeline_running():
            if not messagebox.askyesno(
                "동기화 실행 중",
                "전체 동기화/프리뷰 파이프라인이 실행 중입니다.\n"
                "추가 네트워크 요청이 대상 사이트에 부하를 줄 수 있습니다.\n\n"
                "그래도 수집 미리보기를 실행할까요?",
                parent=self.dialog,
            ):
                return
        if not self._warn_private_url(snap["url"]):
            return
        gen = self._begin_work("수집 미리보기 실행 중… (최대 몇 초 소요)")
        if gen is None:
            return
        snap = dict(snap)
        try:
            snap["limit"] = min(int(snap.get("limit") or 3), 3)
        except (TypeError, ValueError):
            snap["limit"] = 3
        snap["type"] = "css"

        def work():
            stats_note = ""
            try:
                from websync.scrapers.css import CssSelectorScraper

                scraper = CssSelectorScraper()
                arts = scraper.fetch_articles(snap)
                stats = getattr(scraper, "last_fetch_stats", {}) or {}
                if stats.get("content_fallback_count"):
                    stats_note = (
                        f"\n\n⚠️ 본문 선택자 미매칭으로 목록 카드 전체를 본문으로 쓴 항목: "
                        f"{stats['content_fallback_count']}건\n"
                        "「상세 페이지 본문」을 켜거나 본문 선택자를 조정하세요."
                    )
                lines = [f"미리보기 성공: {len(arts)}건"]
                for i, a in enumerate(arts, 1):
                    title = (a.get("title") or "")[:60]
                    url = (a.get("url") or "")[:80]
                    body = (a.get("content") or "")
                    plain = body[:120].replace("\n", " ")
                    flag = " [목록폴백]" if a.get("_content_fallback") else ""
                    lines.append(f"\n[{i}]{flag} {title}\n  URL: {url}\n  본문: {plain}…")
                msg = ("\n".join(lines) if arts else "수집 결과 0건") + stats_note
            except Exception as e:
                msg = f"미리보기 실패:\n{e}"
            self._schedule(gen, lambda: self._finish_preview(msg, gen))

        threading.Thread(target=work, daemon=True).start()

    def _finish_preview(self, msg: str, gen: int) -> None:
        if gen != self._req_gen:
            return
        self._busy = False
        if not self._dialog_alive():
            return
        self._set_result(msg)
        ok = not msg.startswith("미리보기 실패")
        warn = "목록폴백" in msg or "본문 선택자 미매칭" in msg
        if ok and warn:
            self._set_status(
                "미리보기 완료 — 본문 폴백 사용됨. 선택자·상세 페이지 옵션을 확인하세요.",
                ok=False,
            )
        else:
            self._set_status(
                "수집 미리보기 완료." if ok else "수집 미리보기 실패 — 선택자를 조정하세요.",
                ok=ok,
            )
