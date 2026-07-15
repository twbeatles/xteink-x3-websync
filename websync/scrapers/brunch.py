"""BrunchScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, extract_rss_link, ensure_article_url, fetch_url
from bs4 import BeautifulSoup
from websync.core.logger import get_logger

class BrunchScraper(BaseScraper):
    """카카오 브런치 전용 스크래퍼"""

    def __init__(self):
        self.logger = get_logger()
        self.last_fetch_stats: dict = {}


    def fetch_articles(self, site_config: dict) -> list:
        self.last_fetch_stats = {"skipped": 0}
        url = site_config.get("url", "")  # 예: https://brunch.co.kr/@authorid
        limit = site_config.get("limit", 5)
        articles = []
        skipped = 0
        try:
            resp = fetch_url(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            # 최신 글 링크 수집
            links = soup.select("a.link_post")[:limit]
            if not links:
                links = soup.select("ul.list_article_m li a")[:limit]
            for a_tag in links:
                href = a_tag.get("href", "")
                if not href:
                    skipped += 1
                    continue
                if not href.startswith("http"):
                    href = "https://brunch.co.kr" + href
                title_tag = a_tag.find("strong") or a_tag.find("h3") or a_tag.find("h4")
                title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
                content = self._fetch_brunch_content(href, site_config)
                if content:
                    href = ensure_article_url(href, url, title)
                    articles.append({"title": title, "content": content, "url": href})
                else:
                    skipped += 1
            self.last_fetch_stats = {"skipped": skipped}
            if links and not articles:
                raise Exception(f"목록 {len(links)}건 중 본문 수집 성공 0건")
        except Exception as e:
            if "본문 수집 성공 0건" in str(e) or "브런치 수집 실패" in str(e):
                raise
            raise Exception(f"브런치 수집 실패: {e}") from e
        return articles

    def _fetch_brunch_content(self, url: str, site_config: dict) -> str:
        try:
            resp = fetch_url(url, timeout=15)
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
            self.logger.warning(f"BrunchScraper 포스트 수집 실패 ({url}): {e}")
            return ""

