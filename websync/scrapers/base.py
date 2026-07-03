"""스크래퍼 공통 기반 및 유틸리티"""
import re
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from urllib.parse import urljoin

from websync.core.article import ensure_article_url

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}


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
