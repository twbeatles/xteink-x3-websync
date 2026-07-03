import os
import json
import secrets
import threading
import copy
from websync.core.paths import PROJECT_ROOT, resolve_path

class ConfigManager:
    """설정 파일(config.json)의 로드 및 저장을 전담하는 클래스"""
    _lock = threading.Lock()

    DEFAULT_SITE = {
        "name": "",
        "type": "css",
        "url": "",
        "item_selector": ".post-item",
        "title_selector": ".post-title",
        "content_selector": ".post-content",
        "remove_selectors": "",
        "limit": 5,
        "enabled": True,
        "include_images": False,
        "translate_to": "",
    }

    DEFAULT_CONFIG = {
        "x3_ip": "crosspoint.local",
        "x3_devices": [],
        "output_dir": "./output",
        "calibre_path": "C:\\Program Files\\Calibre2\\calibredb.exe",
        "font_family": "serif",
        "font_size": 16,
        "line_height": 1.7,
        "epub_cover": True,
        "sites": [
            {
                "name": "예시 블로그 (일반 웹)",
                "type": "css",
                "url": "https://example.com/blog",
                "item_selector": ".post-item",
                "title_selector": ".post-title",
                "content_selector": ".post-content",
                "remove_selectors": ".ad-banner, .reply-box",
                "limit": 5,
                "enabled": True,
                "include_images": False,
                "translate_to": "",
            },
            {
                "name": "예시 뉴스 피드 (RSS)",
                "type": "rss",
                "url": "https://example.com/feed.xml",
                "limit": 5,
                "enabled": False,
                "include_images": False,
                "translate_to": "",
            }
        ],
        "schedule": {
            "enabled": False,
            "hour": "07",
            "minute": "00"
        },
        "ai_summary": {
            "enabled": False,
            "provider": "openai",
            "api_key": "",
            "model": "gpt-4o-mini",
            "ollama_host": "http://localhost:11434"
        },
        "translation": {
            "enabled": False,
            "provider": "googletrans",
            "libretranslate_host": "http://localhost:5000",
            "libretranslate_api_key": ""
        },
        "opds_server": {
            "enabled": False,
            "port": 8765,
            "bind_host": "127.0.0.1",
            "allow_lan": False
        },
        "web_dashboard": {
            "enabled": False,
            "port": 8766,
            "bind_host": "127.0.0.1",
            "allow_lan": False,
            "api_token": ""
        },
        "calibre_watch": {
            "enabled": False,
            "watch_dir": ""
        }
    }

    def __init__(self, config_path: str | None = None):
        if config_path is None:
            self.config_path = os.path.join(PROJECT_ROOT, "config.json")
        else:
            self.config_path = resolve_path(config_path)

    @classmethod
    def _deep_merge(cls, default: dict, current: dict) -> tuple[dict, bool]:
        """default를 기준으로 current에 결손 키를 재귀 보강합니다."""
        updated = False
        result = copy.deepcopy(current)
        for key, default_val in default.items():
            if key not in result:
                result[key] = copy.deepcopy(default_val)
                updated = True
            elif isinstance(default_val, dict) and isinstance(result.get(key), dict):
                merged, sub_updated = cls._deep_merge(default_val, result[key])
                if sub_updated:
                    result[key] = merged
                    updated = True
        return result, updated

    @classmethod
    def _merge_sites(cls, sites: list) -> tuple[list, bool]:
        """사이트 항목별 결손 필드를 DEFAULT_SITE 기준으로 보강합니다."""
        updated = False
        merged_sites = []
        for site in sites:
            if not isinstance(site, dict):
                continue
            merged, changed = cls._deep_merge(cls.DEFAULT_SITE, site)
            merged_sites.append(merged)
            if changed:
                updated = True
        return merged_sites, updated

    def _ensure_api_token(self, config: dict) -> bool:
        """웹 대시보드 API 토큰이 없으면 자동 생성합니다."""
        web = config.get("web_dashboard")
        if not isinstance(web, dict):
            return False
        if web.get("api_token"):
            return False
        web["api_token"] = secrets.token_urlsafe(24)
        return True

    def load_config(self) -> dict:
        with self._lock:
            if not os.path.exists(self.config_path):
                cfg = copy.deepcopy(self.DEFAULT_CONFIG)
                self._ensure_api_token(cfg)
                self._save_config_unlocked(cfg)
                return cfg
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)

                config, updated = self._deep_merge(self.DEFAULT_CONFIG, config)

                if "sites" in config and isinstance(config["sites"], list):
                    merged_sites, sites_updated = self._merge_sites(config["sites"])
                    config["sites"] = merged_sites
                    updated = updated or sites_updated

                if self._ensure_api_token(config):
                    updated = True

                if updated:
                    self._save_config_unlocked(config)
                return config
            except Exception as e:
                print(f"⚠️ 설정 로드 실패: {e}. 기본값을 사용합니다.")
                return copy.deepcopy(self.DEFAULT_CONFIG)

    def save_config(self, config_data: dict):
        with self._lock:
            self._save_config_unlocked(config_data)

    def _save_config_unlocked(self, config_data: dict):
        """락이 이미 잡힌 상태에서 호출하는 내부 저장 전용 함수"""
        try:
            os.makedirs(os.path.dirname(self.config_path) or ".", exist_ok=True)
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ 설정 저장 실패: {e}")

    def get_resolved_output_dir(self, config: dict | None = None) -> str:
        cfg = config or self.load_config()
        return resolve_path(cfg.get("output_dir", "./output"))
