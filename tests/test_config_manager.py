import json
import os
import tempfile

import pytest

from unittest.mock import patch

from websync.config.exceptions import ConfigLoadError, ConfigSaveError
from websync.config.manager import ConfigManager


def test_deep_merge_adds_nested_keys():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"x3_ip": "192.168.1.1", "sites": [{"name": "A", "type": "rss", "url": "http://x"}]}, f)

        cm = ConfigManager(path)
        cfg = cm.load_config()

        assert "ai_summary" in cfg
        assert cfg["ai_summary"]["enabled"] is False
        assert cfg["sites"][0].get("include_images") is False
        assert "api_token" in cfg.get("web_dashboard", {})
        assert "calibre_library_path" in cfg


def test_atomic_save_writes_valid_json():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        cm = ConfigManager(path)
        cfg = cm.load_config()
        cfg["x3_ip"] = "10.0.0.5"
        cm.save_config(cfg)
        with open(path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["x3_ip"] == "10.0.0.5"
        assert os.path.exists(f"{path}.bak")


def test_corrupt_json_raises_and_preserves():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write("{not valid json")
        cm = ConfigManager(path)
        with pytest.raises(ConfigLoadError) as exc:
            cm.load_config()
        assert exc.value.corrupt_path and os.path.exists(exc.value.corrupt_path)


def test_save_config_raises_on_failure():
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "config.json")
        cm = ConfigManager(path)
        cfg = cm.load_config()
        with patch("builtins.open", side_effect=OSError("disk full")):
            with pytest.raises(ConfigSaveError):
                cm.save_config(cfg)