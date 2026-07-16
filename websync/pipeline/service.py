import threading
from typing import Callable, Optional

from websync.epub.builder import EpubBuilder
from websync.upload.uploader import X3Uploader
from websync.config.manager import ConfigManager
from websync.db.history import SyncHistoryDb
from websync.core.logger import get_logger
from websync.core.process_lock import ProcessFileLock
from websync.pipeline.article_keys import article_sync_key
from websync.pipeline.sync_pipeline import run_sync_pipeline_locked
from websync.pipeline.preview import preview_articles as run_preview_articles
from websync.pipeline.selected_sync import sync_selected_articles as run_sync_selected_articles


class SyncService:
    """전체 동기화 비즈니스 로직 조율을 전담하는 파사드 (SOLID: SRP/DIP)."""

    _pipeline_lock = threading.Lock()
    _process_lock = ProcessFileLock()

    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = self.config_manager.load_config()
        self.db = SyncHistoryDb()
        self.logger = get_logger()
        self._last_pipeline_result: dict = {}
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
        df = self.config.get("device_files") or {}
        self.uploader = X3Uploader(
            x3_ip=self.config.get("x3_ip", "crosspoint.local"),
            devices=self.config.get("x3_devices", []),
            remote_dir=df.get("default_upload_path", "/"),
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
        return article_sync_key(article, site_name, base_url)

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
        return run_sync_pipeline_locked(self, log_callback, progress_callback)

    def preview_articles(
        self,
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> list[dict]:
        return run_preview_articles(self, log_callback, progress_callback)

    def sync_selected_articles(
        self,
        selected_articles: list[dict],
        log_callback: Optional[Callable[[str], None]] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None
    ) -> bool:
        return run_sync_selected_articles(
            self, selected_articles, log_callback, progress_callback
        )
