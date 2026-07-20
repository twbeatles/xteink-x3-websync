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
        with patch("websync.pipeline.sync_pipeline.ToastNotifier.show_toast"):
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
    svc.db.needs_sync = MagicMock(return_value=False)
    with patch.object(ScraperFactory, "get_scraper") as mock_get:
        mock_get.return_value.fetch_articles.return_value = [
            {"title": "t", "content": "<p>x</p>", "url": "https://ex.com/1"},
        ]
        with patch("websync.pipeline.sync_pipeline.ToastNotifier.show_toast"):
            result = svc.run_sync_pipeline()
    assert result is True
    assert svc.get_last_pipeline_result()["status"] == "no_new"


def test_pipeline_partial_upload_marks_only_successful_devices():
    cm = MagicMock(spec=ConfigManager)
    cfg = _base_config([
        {"name": "A", "type": "rss", "url": "https://ex.com/feed", "enabled": True, "limit": 1},
    ])
    cfg["x3_devices"] = [{"name": "추가", "ip": "10.0.0.2"}]
    cm.load_config.return_value = cfg
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    svc.db.needs_sync = MagicMock(return_value=True)
    svc.db.is_synced_for_device = MagicMock(return_value=False)
    svc.db.mark_synced_many = MagicMock(return_value=1)
    with patch.object(svc, "_reload_config"):
        with patch.object(svc, "maybe_backup_pull", return_value={"skipped": True}):
            with patch.object(svc, "maybe_backup_push", return_value={"skipped": True}):
                with patch.object(ScraperFactory, "get_scraper") as mock_get:
                    mock_get.return_value.fetch_articles.return_value = [
                        {"title": "t", "content": "<p>x</p>", "url": "https://ex.com/1"},
                    ]
                    with patch.object(svc.epub_builder, "build", return_value="/tmp/test.epub"):
                        with patch.object(
                            svc.uploader,
                            "upload_to_targets",
                            return_value={"127.0.0.1": True, "10.0.0.2": False},
                        ) as mock_upload:
                            with patch("websync.pipeline.sync_pipeline.ToastNotifier.show_toast"):
                                result = svc.run_sync_pipeline()
    assert result is False
    svc.db.mark_synced_many.assert_called_once()
    entries = svc.db.mark_synced_many.call_args.args[0]
    assert len(entries) == 1
    assert entries[0]["device_ip"] == "127.0.0.1"
    # only_ips 에 미전송 기기 전달
    assert mock_upload.call_args.kwargs.get("only_ips") == ["127.0.0.1", "10.0.0.2"]


def test_pipeline_skips_already_synced_device_on_retry():
    cm = MagicMock(spec=ConfigManager)
    cfg = _base_config([
        {"name": "A", "type": "rss", "url": "https://ex.com/feed", "enabled": True, "limit": 1},
    ])
    cfg["x3_ip"] = "10.0.0.1"
    cfg["x3_devices"] = [{"name": "B", "ip": "10.0.0.2"}]
    cm.load_config.return_value = cfg
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    svc.db.needs_sync = MagicMock(return_value=True)

    def synced_side(url, ip):
        return ip == "10.0.0.1"

    svc.db.is_synced_for_device = MagicMock(side_effect=synced_side)
    svc.db.mark_synced_many = MagicMock(return_value=1)
    with patch.object(svc, "_reload_config"):
        with patch.object(svc, "maybe_backup_pull", return_value={"skipped": True}):
            with patch.object(svc, "maybe_backup_push", return_value={"skipped": True}):
                with patch.object(ScraperFactory, "get_scraper") as mock_get:
                    mock_get.return_value.fetch_articles.return_value = [
                        {"title": "t", "content": "<p>x</p>", "url": "https://ex.com/1"},
                    ]
                    with patch.object(svc.epub_builder, "build", return_value="/tmp/test.epub"):
                        with patch.object(
                            svc.uploader,
                            "upload_to_targets",
                            return_value={"10.0.0.2": True},
                        ) as mock_upload:
                            with patch("websync.pipeline.sync_pipeline.ToastNotifier.show_toast"):
                                result = svc.run_sync_pipeline()
    assert result is True
    assert mock_upload.call_args.kwargs.get("only_ips") == ["10.0.0.2"]
    entries = svc.db.mark_synced_many.call_args.args[0]
    assert entries[0]["device_ip"] == "10.0.0.2"


def test_pipeline_all_empty_fetch_returns_false():
    cm = MagicMock(spec=ConfigManager)
    cm.load_config.return_value = _base_config([
        {"name": "A", "type": "rss", "url": "https://ex.com/feed", "enabled": True, "limit": 1},
        {"name": "B", "type": "youtube", "url": "https://ex.com/videos.xml", "enabled": True, "limit": 1},
    ])
    cm.get_resolved_output_dir.return_value = "./output"

    svc = SyncService(cm)
    with patch.object(ScraperFactory, "get_scraper") as mock_get:
        mock_get.return_value.fetch_articles.return_value = []
        with patch("websync.pipeline.sync_pipeline.ToastNotifier.show_toast"):
            result = svc.run_sync_pipeline()
    assert result is False
    assert svc.get_last_pipeline_result()["status"] == "empty_fetch"


def test_last_pipeline_result_is_instance_variable():
    """_last_pipeline_result가 인스턴스 변수로 각 인스턴스마다 독립되어야 함."""
    cm1 = MagicMock(spec=ConfigManager)
    cm1.load_config.return_value = _base_config()
    cm1.get_resolved_output_dir.return_value = "./output"
    svc1 = SyncService(cm1)
    svc1._last_pipeline_result = {"status": "test_instance_1", "success": True}

    cm2 = MagicMock(spec=ConfigManager)
    cm2.load_config.return_value = _base_config()
    cm2.get_resolved_output_dir.return_value = "./output"
    svc2 = SyncService(cm2)

    assert svc2._last_pipeline_result == {} or svc2._last_pipeline_result.get("status") != "test_instance_1"
    assert svc1._last_pipeline_result["status"] == "test_instance_1"