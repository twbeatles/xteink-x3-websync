import os
import threading
from typing import Callable, Optional
from websync.scrapers import ScraperFactory
from websync.epub.builder import EpubBuilder
from websync.upload.uploader import X3Uploader
from websync.integrations.notifier import ToastNotifier
from websync.config.manager import ConfigManager
from websync.db.history import SyncHistoryDb
from websync.core.logger import get_logger
from websync.pipeline.summarizer import Summarizer
from websync.pipeline.translator import Translator
from websync.core.article import ensure_article_url
from websync.core.paths import resolve_path

class SyncService:
    """전체 동기화 비즈니스 로직 조율을 전담하는 클래스"""
    _pipeline_lock = threading.Lock()

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
            line_height=self.config.get("line_height", 1.7)
        )
        self.uploader = X3Uploader(
            x3_ip=self.config.get("x3_ip", "crosspoint.local"),
            devices=self.config.get("x3_devices", [])
        )

    def is_pipeline_running(self) -> bool:
        return self._pipeline_lock.locked()

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

        try:
            return self._run_sync_pipeline_locked(log_callback, progress_callback)
        finally:
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
            return False

        total_sites = len(enabled_sites)
        success_count = 0
        actual_work_sites = 0
        generate_cover = self.config.get("epub_cover", True)

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

                if not articles:
                    log(f"⚠️ [{name}] 수집된 기사가 없어 건너뜁니다. (URL·스크래퍼 설정·네트워크를 확인하세요)")
                    continue

                for art in articles:
                    art["url"] = self._article_sync_key(art, name, base_url)

                new_articles = [
                    art for art in articles
                    if art.get("url") and not self.db.is_synced(art["url"])
                ]

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

                log(f"📚 [{name}] EPUB 문서 제작 중...")
                epub_path = self.epub_builder.build(name, new_articles, generate_cover=generate_cover)
                log(f"   => 파일 생성: {os.path.basename(epub_path)}")

                upload_results = self.uploader.upload_to_targets(epub_path)
                for dev_name, ok in upload_results.items():
                    status = "✅" if ok else "❌"
                    log(f"   => {status} [{dev_name}] 전송")

                upload_ok = bool(upload_results) and all(upload_results.values())

                if upload_ok:
                    log(f"🎉 [{name}] 동기화 완료 및 전송 성공!")
                    for art in new_articles:
                        self.db.mark_synced(art["url"], name, art.get("title"))
                    success_count += 1
                else:
                    log(f"❌ [{name}] 전송 실패! 기기가 켜져 있고 Wi-Fi 상태인지 확인하세요.")

            except Exception as e:
                self.logger.exception(f"[{name}] 처리 중 오류: {e}")
                log(f"❌ [{name}] 처리 중 오류 발생: {e}")

        if progress_callback:
            progress_callback(total_sites, total_sites)

        if actual_work_sites == 0:
            log("\n📊 작업 결과 요약: 모든 등록 사이트에 전송할 신규 포스트가 없습니다. (기기 전송 생략)")
            ToastNotifier.show_toast(
                "X3 WebSync 상태",
                "모든 뉴스 사이트/블로그에 새로 업로드된 신규 기사가 없어 전송을 생략했습니다."
            )
            return True

        log(f"\n📊 작업 결과 요약: {success_count} / {actual_work_sites} 개 신규 소식 사이트 동기화 전송 완료.")

        if success_count > 0:
            ToastNotifier.show_toast(
                "X3 WebSync 동기화 완료",
                f"신규 업데이트된 {success_count}개 사이트 소식이 무선 전송되었습니다."
            )
        else:
            ToastNotifier.show_toast(
                "X3 WebSync 동기화 실패",
                "신규 포스트 전송 과정에 오류가 발생했습니다. (기기 연결 상태 확인 요망)",
                is_error=True
            )

        return success_count > 0
