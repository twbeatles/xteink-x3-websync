import json
import os
import tempfile
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