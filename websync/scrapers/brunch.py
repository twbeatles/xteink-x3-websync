"""BrunchScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, extract_rss_link, ensure_article_url
import requests
from bs4 import BeautifulSoup

class BrunchScraper(BaseScraper):
    """카카오 브런치 전용 스크래퍼"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url", "")  # 예: https://brunch.co.kr/@authorid
        limit = site_config.get("limit", 5)
        articles = []
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            # 최신 글 링크 수집
            links = soup.select("a.link_post")[:limit]
            if not links:
                links = soup.select("ul.list_article_m li a")[:limit]
            for a_tag in links:
                href = a_tag.get("href", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = "https://brunch.co.kr" + href
                title_tag = a_tag.find("strong") or a_tag.find("h3") or a_tag.find("h4")
                title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
                content = self._fetch_brunch_content(href, site_config)
                if content:
                    href = ensure_article_url(href, url, title)
                    articles.append({"title": title, "content": content, "url": href})
        except Exception as e:
            print(f"❌ BrunchScraper 오류: {e}")
        return articles

    def _fetch_brunch_content(self, url: str, site_config: dict) -> str:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            content_tag = (
                soup.find("div", class_="wrap_article_body") or
                soup.find("div", class_="article_body") or
                soup.find("article")
            )
            if not content_tag:
                return ""
            for tag in content_tag.find_all(True):
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("href",)}
            maybe_strip_images(content_tag, site_config)
            return str(content_tag)
        except Exception as e:
            print(f"⚠️ BrunchScraper 포스트 수집 실패 ({url}): {e}")
            return ""
