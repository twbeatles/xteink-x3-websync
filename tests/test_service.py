import threading
import time
from unittest.mock import MagicMock, patch

from websync.config.manager import ConfigManager
from websync.pipeline.service import SyncService
from websync.scrapers.factory import ScraperFactory


def test_pipeline_lock_prevents_concurrent_run():
    cm = MagicMock(spec=ConfigManager)
    cm.load_config.return_value = {
        "x3_ip": "127.0.0.1",
        "x3_devices": [],
        "output_dir": "./output",
        "font_family": "serif",
        "font_size": 16,
        "line_height": 1.7,
        "epub_cover": False,
        "sites": [],
        "ai_summary": {"enabled": False},
        "translation": {"enabled": False},
    }
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    started = threading.Event()
    release = threading.Event()

    def slow_pipeline(*args, **kwargs):
        started.set()
        release.wait(timeout=5)

    with patch.object(svc, "_run_sync_pipeline_locked", side_effect=slow_pipeline):
        t = threading.Thread(target=svc.run_sync_pipeline)
        t.start()
        assert started.wait(timeout=2)
        assert svc.is_pipeline_running()
        assert svc.run_sync_pipeline() is False
        release.set()
        t.join(timeout=2)
        assert not svc.is_pipeline_running()


def _base_config(sites=None):
    return {
        "x3_ip": "127.0.0.1",
        "x3_devices": [],
        "output_dir": "./output",
        "font_family": "serif",
        "font_size": 16,
        "line_height": 1.7,
        "epub_cover": False,
        "sites": sites or [],
        "ai_summary": {"enabled": False},
        "translation": {"enabled": False},
    }


def test_pipeline_all_site_errors_returns_false():
    cm = MagicMock(spec=ConfigManager)
    cm.load_config.return_value = _base_config([
        {"name": "A", "type": "css", "url": "https://ex.com", "enabled": True, "limit": 1},
    ])
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    with patch.object(ScraperFactory, "get_scraper") as mock_get:
        mock_get.return_value.fetch_articles.side_effect = RuntimeError("network down")
        with patch("websync.pipeline.service.ToastNotifier.show_toast"):
            result = svc.run_sync_pipeline()
    assert result is False
    assert svc.get_last_pipeline_result()["status"] == "errors"


def test_pipeline_no_new_articles_returns_true():
    cm = MagicMock(spec=ConfigManager)
    cm.load_config.return_value = _base_config([
        {"name": "A", "type": "rss", "url": "https://ex.com/feed", "enabled": True, "limit": 1},
    ])
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    svc.db.is_synced = MagicMock(return_value=True)
    with patch.object(ScraperFactory, "get_scraper") as mock_get:
        mock_get.return_value.fetch_articles.return_value = [
            {"title": "t", "content": "<p>x</p>", "url": "https://ex.com/1"},
        ]
        with patch("websync.pipeline.service.ToastNotifier.show_toast"):
            result = svc.run_sync_pipeline()
    assert result is True
    assert svc.get_last_pipeline_result()["status"] == "no_new"


def test_pipeline_partial_upload_marks_synced():
    cm = MagicMock(spec=ConfigManager)
    cfg = _base_config([
        {"name": "A", "type": "rss", "url": "https://ex.com/feed", "enabled": True, "limit": 1},
    ])
    cfg["x3_devices"] = [{"name": "추가", "ip": "10.0.0.2"}]
    cm.load_config.return_value = cfg
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    svc.db.is_synced = MagicMock(return_value=False)
    svc.db.mark_synced = MagicMock()
    with patch.object(svc, "_reload_config"):
        with patch.object(ScraperFactory, "get_scraper") as mock_get:
            mock_get.return_value.fetch_articles.return_value = [
                {"title": "t", "content": "<p>x</p>", "url": "https://ex.com/1"},
            ]
            with patch.object(svc.epub_builder, "build", return_value="/tmp/test.epub"):
                with patch.object(
                    svc.uploader,
                    "upload_to_targets",
                    return_value={"기본 기기": True, "추가": False},
                ):
                    with patch("websync.pipeline.service.ToastNotifier.show_toast"):
                        result = svc.run_sync_pipeline()
    assert result is False
    svc.db.mark_synced.assert_called_once()