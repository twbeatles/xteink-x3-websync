import threading
import time
from unittest.mock import MagicMock, patch

from websync.config.manager import ConfigManager
from websync.pipeline.service import SyncService


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