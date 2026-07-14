import os
import threading
from typing import Callable, Optional
from websync.scrapers import ScraperFactory
from websync.epub.builder import EpubBuilder
from websync.upload.uploader import X3Uploader
from websync.integrations.notifier import ToastNotifier
from websync.config.manager import ConfigManager
from websync.db.history import SyncHistoryDb, SyncHistoryDbError
from websync.core.logger import get_logger
from websync.pipeline.summarizer import Summarizer
from websync.pipeline.translator import Translator
from websync.core.article import ensure_article_url
from websync.core.process_lock import ProcessFileLock


class SyncService:
    """전체 동기화 비즈니스 로직 조율을 전담하는 클래스"""
    _pipeline_lock = threading.Lock()
    _last_pipeline_result: dict = {}
    _process_lock = ProcessFileLock()

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = self.config_manager.load_config()
        self.db = SyncHistoryDb()
        self.logger = get_logger()
        self._apply_config_to_components()

    def _apply_config_to_components(self):
        self.epub_builder = EpubBuilder(
            output_dir=self.config_manager.get_resolved_output_dir(self.config),
            font_family=self.config.get("font_family", "serif"),
            font_size=self.config.get("font_size", 16),
            line_height=self.config.get("line_height", 1.7),
            epub_theme=self.config.get("epub_theme", "default"),
            epub_custom_css=self.config.get("epub_custom_css", "")
        )
        self.uploader = X3Uploader(
            x3_ip=self.config.get("x3_ip", "crosspoint.local"),
            devices=self.config.get("x3_devices", [])
        )


    def is_pipeline_running(self) -> bool:
        if self._pipeline_lock.locked() or self._process_lock.held:
            return True
        return self._process_lock.is_held_by_other()

    def get_last_pipeline_result(self) -> dict:
        return dict(self._last_pipeline_result)

    def _reload_config(self):
        """최신 설정을 리로드하고 서비스 컴포넌트에 반영"""
        self.config = self.config_manager.load_config()
        self._apply_config_to_components()

    @staticmethod
    def _article_sync_key(article: dict, site_name: str, base_url: str) -> str:
        url = ensure_article_url(
            article.get("url", ""),
            base_url,
            article.get("title", "")
        )
        return url

    def run_sync_pipeline(
        self,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        동기화 파이프라인 실행.
        Returns:
            bool: True이면 성공 또는 신규 기사 없음 / False이면 오류 또는 이미 실행 중
        """
        if not self._pipeline_lock.acquire(blocking=False):
            msg = "⚠️ 동기화가 이미 실행 중입니다. 완료 후 다시 시도해 주세요."
            self.logger.warning(msg)
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
            return False

        if not self._process_lock.acquire(blocking=False):
            self._pipeline_lock.release()
            msg = "⚠️ 다른 프로세스에서 동기화가 실행 중입니다. 완료 후 다시 시도해 주세요."
            self.logger.warning(msg)
            if log_callback:
                log_callback(msg)
            else:
                print(msg)
            return False

        try:
            return self._run_sync_pipeline_locked(log_callback, progress_callback)
        finally:
            self._process_lock.release()
            self._pipeline_lock.release()

    def _run_sync_pipeline_locked(
        self,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        def log(msg: str):
            self.logger.info(msg)
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        log("✨ 동기화 프로세스를 실행합니다...")
        self._reload_config()

        summarizer = Summarizer(self.config)
        translator = Translator(self.config)

        enabled_sites = [s for s in self.config.get("sites", []) if s.get("enabled", True)]
        if not enabled_sites:
            log("⚠️ 활성화된 수집 대상 사이트가 설정에 없습니다.")
            ToastNotifier.show_toast("X3 WebSync 실패", "동기화가 중단되었습니다. 활성화된 사이트가 없습니다.", is_error=True)
            self._last_pipeline_result = {"status": "no_sites", "success": False}
            return False

        total_sites = len(enabled_sites)
        success_count = 0
        partial_count = 0
        actual_work_sites = 0
        site_errors = 0
        empty_fetch_sites = 0
        generate_cover = self.config.get("epub_cover", True)
        upload_targets = self.uploader._build_target_list()
        target_ips = [d["ip"] for d in upload_targets]
        ip_to_name = {d["ip"]: d["name"] for d in upload_targets}

        epub_merge_mode = self.config.get("epub_merge_mode", "per_site")
        digest_articles = {}  # {site_name: [new_articles]}

        for site_idx, site in enumerate(enabled_sites):
            name = site.get("name", "무명 사이트")
            scraper_type = site.get("type", "css")
            base_url = site.get("url", "")
            translate_to = site.get("translate_to", "").strip()

            if progress_callback:
                progress_callback(site_idx, total_sites)

            log(f"\n[📰 {name}] ({scraper_type.upper()}) 글 수집 중...")
            try:
                scraper = ScraperFactory.get_scraper(scraper_type)
                articles = scraper.fetch_articles(site)

                fetch_stats = getattr(scraper, "last_fetch_stats", None) or {}
                skipped_items = int(fetch_stats.get("skipped", 0) or 0)
                if skipped_items:
                    log(f"   => ⚠️ 수집 중 개별 스킵 {skipped_items}건 (본문·자막 실패 등)")

                if not articles:
                    empty_fetch_sites += 1
                    log(f"⚠️ [{name}] 수집된 기사가 없어 건너뜁니다. (URL·스크래퍼 설정·네트워크를 확인하세요)")
                    continue

                for art in articles:
                    art["url"] = self._article_sync_key(art, name, base_url)

                new_articles = []
                for art in articles:
                    url = art.get("url")
                    if not url:
                        continue
                    if self.db.needs_sync(url, target_ips):
                        new_articles.append(art)

                skipped = len(articles) - len(new_articles)
                if skipped:
                    log(f"   => 💡 중복 제외 {skipped}건 (이미 전송된 포스트)")

                if not new_articles:
                    log(f"   => 💡 [{name}] 전송할 신규 포스트가 없습니다.")
                    continue

                actual_work_sites += 1
                log(f"📦 [{name}] 신규 포스트 {len(new_articles)}개 검출. 후처리 중...")

                if translate_to and translator.is_available_for_site(translate_to):
                    log(f"   => 🌐 [{name}] '{translate_to}' 언어로 번역 중...")
                    for art in new_articles:
                        art["content"] = translator.translate_html(art["content"], target_lang=translate_to)

                if summarizer.is_available():
                    log(f"   => 🤖 [{name}] AI 요약 생성 중...")
                    for art in new_articles:
                        art["summary_html"] = summarizer.summarize(art.get("title", ""), art.get("content", ""))

                if epub_merge_mode == "daily_digest":
                    # 일간 합본을 위해 기사를 축적
                    digest_articles[name] = new_articles
                    log(f"   => 💡 [{name}] 합본 대기열에 추가됨 ({len(new_articles)}건)")
                else:
                    # 기존 방식: 사이트별 개별 빌드 및 전송
                    # 이번 배치 중 하나라도 미전송인 기기만 업로드 대상
                    pending_ips = []
                    pending_set = set()
                    for ip in target_ips:
                        if any(not self.db.is_synced_for_device(art["url"], ip) for art in new_articles):
                            if ip not in pending_set:
                                pending_set.add(ip)
                                pending_ips.append(ip)

                    if not pending_ips:
                        log(f"   => 💡 [{name}] 전송할 대상 기기가 없습니다.")
                        continue

                    if len(pending_ips) < len(target_ips):
                        names = [ip_to_name.get(ip, ip) for ip in pending_ips]
                        log(f"   => 📡 미전송 기기만 전송: {', '.join(names)}")

                    log(f"📚 [{name}] EPUB 문서 제작 중...")
                    epub_path = self.epub_builder.build(name, new_articles, generate_cover=generate_cover)
                    log(f"   => 파일 생성: {os.path.basename(epub_path)}")

                    upload_results = self.uploader.upload_to_targets(epub_path, only_ips=pending_ips)
                    for ip, ok in upload_results.items():
                        status = "✅" if ok else "❌"
                        detail = ""
                        if not ok:
                            err = getattr(self.uploader, "last_errors", {}).get(ip)
                            if err:
                                detail = f" — {err}"
                        log(f"   => {status} [{ip_to_name.get(ip, ip)}] ({ip}) 전송{detail}")

                    any_ok = bool(upload_results) and any(upload_results.values())
                    all_ok = bool(upload_results) and all(upload_results.values()) and set(upload_results) == set(pending_ips)

                    if any_ok:
                        for ip, ok in upload_results.items():
                            if not ok:
                                continue
                            for art in new_articles:
                                if not self.db.is_synced_for_device(art["url"], ip):
                                    self.db.mark_synced(
                                        art["url"], name, art.get("title", ""), device_ip=ip
                                    )
                        if all_ok:
                            log(f"🎉 [{name}] 동기화 완료 및 전송 성공!")
                            success_count += 1
                        else:
                            failed = [ip_to_name.get(ip, ip) for ip, ok in upload_results.items() if not ok]
                            log(
                                f"⚠️ [{name}] 일부 기기 전송 실패: {', '.join(failed)} "
                                f"(성공 기기만 이력 기록, 실패 기기는 다음 동기화에서 재시도)"
                            )
                            partial_count += 1
                    else:
                        log(f"❌ [{name}] 전송 실패! 기기가 켜져 있고 Wi-Fi 상태인지 확인하세요.")

            except SyncHistoryDbError as e:
                self.logger.error(str(e))
                log(f"❌ [{name}] DB 오류로 중단: {e}")
                self._last_pipeline_result = {"status": "db_error", "success": False, "message": str(e)}
                ToastNotifier.show_toast("X3 WebSync DB 오류", str(e), is_error=True)
                return False
            except Exception as e:
                site_errors += 1
                self.logger.exception(f"[{name}] 처리 중 오류: {e}")
                log(f"❌ [{name}] 처리 중 오류 발생: {e}")

        # 일간 합본 처리 진행 (epub_merge_mode == "daily_digest" 일 경우)
        if epub_merge_mode == "daily_digest" and digest_articles:
            log("\n=== 📚 일간 합본(Daily Digest) 빌드 및 전송 시작 ===")
            try:
                # 모든 축적된 기사의 URL 목록
                all_new_urls = []
                for site_name, arts in digest_articles.items():
                    for art in arts:
                        all_new_urls.append((art["url"], site_name, art.get("title", "")))

                # 이번 배치 기사 중 미전송된 기기가 있는 기기 추출
                pending_ips = []
                pending_set = set()
                for ip in target_ips:
                    if any(not self.db.is_synced_for_device(url, ip) for url, _, _ in all_new_urls):
                        if ip not in pending_set:
                            pending_set.add(ip)
                            pending_ips.append(ip)

                if pending_ips:
                    log(f"📚 합본 문서 제작 중... (총 {len(digest_articles)}개 사이트, {len(all_new_urls)}개 기사)")
                    epub_path = self.epub_builder.build_digest(digest_articles, generate_cover=generate_cover)
                    log(f"   => 파일 생성: {os.path.basename(epub_path)}")

                    upload_results = self.uploader.upload_to_targets(epub_path, only_ips=pending_ips)
                    for ip, ok in upload_results.items():
                        status = "✅" if ok else "❌"
                        detail = ""
                        if not ok:
                            err = getattr(self.uploader, "last_errors", {}).get(ip)
                            if err:
                                detail = f" — {err}"
                        log(f"   => {status} [{ip_to_name.get(ip, ip)}] ({ip}) 전송{detail}")

                    any_ok = bool(upload_results) and any(upload_results.values())
                    all_ok = bool(upload_results) and all(upload_results.values()) and set(upload_results) == set(pending_ips)

                    if any_ok:
                        for ip, ok in upload_results.items():
                            if not ok:
                                continue
                            for url, site_name, title in all_new_urls:
                                if not self.db.is_synced_for_device(url, ip):
                                    self.db.mark_synced(url, site_name, title, device_ip=ip)
                        if all_ok:
                            log("🎉 일간 합본 동기화 완료 및 전송 성공!")
                            success_count = actual_work_sites
                        else:
                            failed = [ip_to_name.get(ip, ip) for ip, ok in upload_results.items() if not ok]
                            log(f"⚠️ 일간 합본 일부 기기 전송 실패: {', '.join(failed)}")
                            partial_count = 1
                    else:
                        log("❌ 일간 합본 전송 실패! 기기 상태를 확인하세요.")
                else:
                    log("💡 전송할 대상 기기가 없어 합본 생성을 건너뜁니다.")
                    success_count = actual_work_sites

            except Exception as e:
                self.logger.exception(f"일간 합본 처리 중 오류: {e}")
                log(f"❌ 일간 합본 처리 중 오류 발생: {e}")
                site_errors += 1

        if progress_callback:
            progress_callback(total_sites, total_sites)

        if actual_work_sites == 0:
            if site_errors > 0:
                log(f"\n📊 작업 결과 요약: {site_errors}개 사이트에서 오류 발생. 로그를 확인하세요.")
                ToastNotifier.show_toast(
                    "X3 WebSync 동기화 실패",
                    f"{site_errors}개 사이트 처리 중 오류가 발생했습니다.",
                    is_error=True,
                )
                self._last_pipeline_result = {"status": "errors", "success": False, "site_errors": site_errors}
                return False
            if empty_fetch_sites == total_sites:
                log(
                    f"\n📊 작업 결과 요약: 활성 사이트 {total_sites}개 모두 수집 결과가 비었습니다. "
                    "스크래퍼 설정·네트워크·의존성 패키지를 확인하세요."
                )
                ToastNotifier.show_toast(
                    "X3 WebSync 동기화 실패",
                    "모든 사이트에서 기사를 수집하지 못했습니다. 로그를 확인하세요.",
                    is_error=True,
                )
                self._last_pipeline_result = {
                    "status": "empty_fetch",
                    "success": False,
                    "empty_fetch_sites": empty_fetch_sites,
                }
                return False
            log("\n📊 작업 결과 요약: 모든 등록 사이트에 전송할 신규 포스트가 없습니다. (기기 전송 생략)")
            ToastNotifier.show_toast(
                "X3 WebSync 상태",
                "모든 뉴스 사이트/블로그에 새로 업로드된 신규 기사가 없어 전송을 생략했습니다."
            )
            self._last_pipeline_result = {"status": "no_new", "success": True}
            return True

        log(f"\n📊 작업 결과 요약: {success_count} / {actual_work_sites} 개 사이트 전체 전송 완료" +
            (f", {partial_count}개 부분 성공" if partial_count else ""))

        overall_ok = success_count == actual_work_sites and site_errors == 0
        self._last_pipeline_result = {
            "status": "completed",
            "success": overall_ok,
            "success_count": success_count,
            "partial_count": partial_count,
            "actual_work_sites": actual_work_sites,
            "site_errors": site_errors,
        }

        if success_count > 0 and overall_ok:
            ToastNotifier.show_toast(
                "X3 WebSync 동기화 완료",
                f"신규 업데이트된 {success_count}개 사이트 소식이 무선 전송되었습니다."
            )
        elif partial_count > 0:
            ToastNotifier.show_toast(
                "X3 WebSync 부분 완료",
                f"{partial_count}개 사이트가 일부 기기에만 전송되었습니다. 로그를 확인하세요.",
                is_error=True,
            )
        else:
            ToastNotifier.show_toast(
                "X3 WebSync 동기화 실패",
                "신규 포스트 전송 과정에 오류가 발생했습니다. (기기 연결 상태 확인 요망)",
                is_error=True
            )

        return overall_ok

    def preview_articles(
        self,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> list[dict]:
        """
        기사를 스크래핑하고 필터링하지만 EPUB 빌드 및 업로드는 생략하고 결과를 반환합니다.
        
        Returns:
            [{"site_name": str, "title": str, "url": str, "content": str, "scraper_type": str}]
        """
        def log(msg: str):
            self.logger.info(msg)
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        if self.is_pipeline_running():
            log("⚠️ 이미 파이프라인이 구동 중이므로 프리뷰를 실행할 수 없습니다.")
            return []

        self._reload_config()
        enabled_sites = [s for s in self.config.get("sites", []) if s.get("enabled", True)]
        if not enabled_sites:
            log("⚠️ 활성화된 수집 대상 사이트가 없습니다.")
            return []

        total_sites = len(enabled_sites)
        upload_targets = self.uploader._build_target_list()
        target_ips = [d["ip"] for d in upload_targets]
        preview_results = []

        for site_idx, site in enumerate(enabled_sites):
            name = site.get("name", "무명 사이트")
            scraper_type = site.get("type", "css")
            base_url = site.get("url", "")

            if progress_callback:
                progress_callback(site_idx, total_sites)

            log(f"\n[📰 {name}] ({scraper_type.upper()}) 기사 스크래핑(프리뷰) 중...")
            try:
                scraper = ScraperFactory.get_scraper(scraper_type)
                articles = scraper.fetch_articles(site)

                if not articles:
                    log(f"⚠️ [{name}] 수집된 기사가 없습니다.")
                    continue

                for art in articles:
                    art["url"] = self._article_sync_key(art, name, base_url)

                new_articles = []
                for art in articles:
                    url = art.get("url")
                    if not url:
                        continue
                    if self.db.needs_sync(url, target_ips):
                        new_articles.append(art)

                log(f"   => 수집: {len(articles)}건 (신규 검출: {len(new_articles)}건)")
                for art in new_articles:
                    preview_results.append({
                        "site_name": name,
                        "title": art.get("title", "제목 없음"),
                        "url": art.get("url", ""),
                        "content": art.get("content", ""),
                        "scraper_type": scraper_type
                    })
            except Exception as e:
                self.logger.exception(f"[{name}] 프리뷰 중 오류: {e}")
                log(f"❌ [{name}] 스크래핑 실패: {e}")

        if progress_callback:
            progress_callback(total_sites, total_sites)

        log(f"\n📊 프리뷰 요약: 총 {len(preview_results)}개의 신규 기사를 검출했습니다.")
        return preview_results

    def sync_selected_articles(
        self,
        selected_articles: list[dict],
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        """
        사용자가 선택한 기사만 EPUB으로 빌드하여 기기로 전송합니다.
        
        Args:
            selected_articles: [{"site_name": str, "title": str, "url": str, "content": str}]
        """
        def log(msg: str):
            self.logger.info(msg)
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        if not selected_articles:
            log("⚠️ 전송할 선택 기사가 없습니다.")
            return False

        if not self._pipeline_lock.acquire(blocking=False):
            log("⚠️ 동기화가 이미 실행 중입니다.")
            return False

        if not self._process_lock.acquire(blocking=False):
            self._pipeline_lock.release()
            log("⚠️ 다른 프로세스에서 동기화가 실행 중입니다.")
            return False

        try:
            self._reload_config()
            generate_cover = self.config.get("epub_cover", True)
            upload_targets = self.uploader._build_target_list()
            target_ips = [d["ip"] for d in upload_targets]
            ip_to_name = {d["ip"]: d["name"] for d in upload_targets}
            epub_merge_mode = self.config.get("epub_merge_mode", "per_site")

            summarizer = Summarizer(self.config)
            
            # site_name 별로 기사 그룹화
            articles_by_site = {}
            for art in selected_articles:
                site_name = art.get("site_name", "기타")
                articles_by_site.setdefault(site_name, []).append(art)

            # AI 요약 후처리 적용
            if summarizer.is_available():
                log("🤖 AI 요약 생성 중...")
                for site_name, arts in articles_by_site.items():
                    for art in arts:
                        if "summary_html" not in art:
                            art["summary_html"] = summarizer.summarize(art.get("title", ""), art.get("content", ""))

            success_count = 0
            partial_count = 0
            actual_work = len(articles_by_site)

            if epub_merge_mode == "daily_digest":
                log("\n=== 📚 선택 기사 일간 합본 빌드 및 전송 ===")
                all_urls = []
                for site_name, arts in articles_by_site.items():
                    for art in arts:
                        all_urls.append((art["url"], site_name, art.get("title", "")))

                pending_ips = []
                for ip in target_ips:
                    if any(not self.db.is_synced_for_device(url, ip) for url, _, _ in all_urls):
                        pending_ips.append(ip)

                if pending_ips:
                    epub_path = self.epub_builder.build_digest(articles_by_site, generate_cover=generate_cover)
                    log(f"   => 파일 생성: {os.path.basename(epub_path)}")

                    upload_results = self.uploader.upload_to_targets(epub_path, only_ips=pending_ips)
                    any_ok = bool(upload_results) and any(upload_results.values())
                    all_ok = bool(upload_results) and all(upload_results.values())

                    if any_ok:
                        for ip, ok in upload_results.items():
                            if not ok:
                                continue
                            for url, site_name, title in all_urls:
                                self.db.mark_synced(url, site_name, title, device_ip=ip)
                        if all_ok:
                            log("🎉 전송 완료!")
                            success_count = actual_work
                        else:
                            failed = [ip_to_name.get(ip, ip) for ip, ok in upload_results.items() if not ok]
                            log(f"⚠️ 일부 전송 실패: {', '.join(failed)}")
                            partial_count = 1
                    else:
                        log("❌ 전송 실패!")
                else:
                    log("💡 이미 모든 기기가 전송되었습니다.")
                    success_count = actual_work
            else:
                # 사이트별 빌드
                for idx, (site_name, arts) in enumerate(articles_by_site.items()):
                    if progress_callback:
                        progress_callback(idx, actual_work)
                    
                    pending_ips = []
                    for ip in target_ips:
                        if any(not self.db.is_synced_for_device(art["url"], ip) for art in arts):
                            pending_ips.append(ip)

                    if not pending_ips:
                        log(f"💡 [{site_name}] 이미 전송 완료되어 건너뜁니다.")
                        success_count += 1
                        continue

                    log(f"📚 [{site_name}] 문서 제작 및 전송 중...")
                    epub_path = self.epub_builder.build(site_name, arts, generate_cover=generate_cover)
                    upload_results = self.uploader.upload_to_targets(epub_path, only_ips=pending_ips)

                    any_ok = bool(upload_results) and any(upload_results.values())
                    all_ok = bool(upload_results) and all(upload_results.values())

                    if any_ok:
                        for ip, ok in upload_results.items():
                            if not ok:
                                continue
                            for art in arts:
                                self.db.mark_synced(art["url"], site_name, art.get("title", ""), device_ip=ip)
                        if all_ok:
                            log(f"🎉 [{site_name}] 전송 성공!")
                            success_count += 1
                        else:
                            failed = [ip_to_name.get(ip, ip) for ip, ok in upload_results.items() if not ok]
                            log(f"⚠️ [{site_name}] 일부 실패: {', '.join(failed)}")
                            partial_count += 1
                    else:
                        log(f"❌ [{site_name}] 전송 실패!")

            if progress_callback:
                progress_callback(actual_work, actual_work)

            overall_ok = success_count == actual_work
            self._last_pipeline_result = {
                "status": "completed",
                "success": overall_ok,
                "success_count": success_count,
                "partial_count": partial_count,
                "actual_work_sites": actual_work,
                "site_errors": 0,
            }
            return overall_ok
        finally:
            self._process_lock.release()
            self._pipeline_lock.release()

