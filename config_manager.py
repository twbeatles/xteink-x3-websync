import os
import json
import threading

class ConfigManager:
    """설정 파일(config.json)의 로드 및 저장을 전담하는 클래스"""
    _lock = threading.Lock() # 다중 스레드 접근 대비 클래스 수준 락 정의

    DEFAULT_CONFIG = {
        "x3_ip": "crosspoint.local", # mDNS 기본값 사용
        "output_dir": "./output",
        "calibre_path": "C:\\Program Files\\Calibre2\\calibredb.exe",
        "font_family": "serif",
        "font_size": 16,
        "line_height": 1.7,
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
                "enabled": True
            },
            {
                "name": "예시 뉴스 피드 (RSS)",
                "type": "rss",
                "url": "https://example.com/feed.xml",
                "limit": 5,
                "enabled": False
            }
        ],
        "schedule": {
            "enabled": False,
            "hour": "07",
            "minute": "00"
        }
    }

    def __init__(self, config_path="config.json"):
        self.config_path = config_path

    def load_config(self) -> dict:
        with self._lock: # 동시 접근 임계 구역 락
            if not os.path.exists(self.config_path):
                # 락이 잡힌 상태이므로 내부 _save_config_unlocked 호출
                self._save_config_unlocked(self.DEFAULT_CONFIG)
                return self.DEFAULT_CONFIG
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    config = json.load(f)
                    
                    # 누락된 신규 설정 보완 및 하위 호환성 보장
                    updated = False
                    for key, val in self.DEFAULT_CONFIG.items():
                        if key not in config:
                            config[key] = val
                            updated = True
                    
                    # schedule 하위 키 검증
                    if "schedule" in config:
                        for s_key, s_val in self.DEFAULT_CONFIG["schedule"].items():
                            if s_key not in config["schedule"]:
                                config["schedule"][s_key] = s_val
                                updated = True
                    
                    if updated:
                        self._save_config_unlocked(config)
                    return config
            except Exception as e:
                print(f"⚠️ 설정 로드 실패: {e}. 기본값을 사용합니다.")
                return self.DEFAULT_CONFIG

    def save_config(self, config_data: dict):
        with self._lock: # 동시 접근 임계 구역 락
            self._save_config_unlocked(config_data)

    def _save_config_unlocked(self, config_data: dict):
        """락이 이미 잡힌 상태에서 호출하는 내부 저장 전용 함수"""
        try:
            with open(self.config_path, "w", encoding="utf-8") as f:
                json.dump(config_data, f, ensure_ascii=False, indent=4)
        except Exception as e:
            print(f"❌ 설정 저장 실패: {e}")

