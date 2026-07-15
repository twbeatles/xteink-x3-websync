"""스크래퍼 공통 기반 및 유틸리티"""
import re
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from urllib.parse import urljoin
from requests.adapters import HTTPAdapter

try:
    from urllib3.util.retry import Retry
except ImportError:
    Retry = None  # urllib3 미설치 시 폴백

from websync.core.article import ensure_article_url

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


def _build_session() -> requests.Session:
    """연결 풀링 + 자동 재시도가 설정된 requests.Session 생성."""
    session = requests.Session()
    if Retry is not None:
        retry = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=(429, 500, 502, 503, 504),
            allowed_methods=("GET", "HEAD"),
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("http://", adapter)
        session.mount("https://", adapter)
    return session


# 모듈 수준 공유 세션 (연결 재사용)
_session = _build_session()


def fetch_url(url: str, headers: dict | None = None, timeout: int = 15) -> requests.Response:
    """재시도 세션을 통해 HTTP GET 요청을 수행합니다.

    모든 스크래퍼는 이 헬퍼를 사용하여 일시적 네트워크 오류에 대한
    자동 재시도(최대 3회, 백오프 0.5초) 및 연결 풀링을 활용합니다.
    """
    merged = dict(HEADERS)
    if headers:
        merged.update(headers)
    return _session.get(url, headers=merged, timeout=timeout)


def maybe_strip_images(element, site_config: dict):
    if site_config.get("include_images", False):
        return
    for img in element.find_all("img"):
        img.decompose()


def extract_rss_link(item, feed_url: str) -> str:
    link_elem = item.find("link")
    if not link_elem:
        return ""
    href = link_elem.get("href")
    if href:
        return href.strip()
    return (link_elem.text or "").strip()


class BaseScraper(ABC):
    @abstractmethod
    def fetch_articles(self, site_config: dict) -> list:
        pass
