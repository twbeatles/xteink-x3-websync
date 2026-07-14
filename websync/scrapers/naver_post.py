"""네이버 포스트(post.naver.com) 전용 스크래퍼

URL 형식: https://post.naver.com/my.naver?memberNo={id}
"""
import re
import requests
from bs4 import BeautifulSoup
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images
from websync.scrapers.naver_common import clean_naver_content
from websync.core.logger import get_logger


class NaverPostScraper(BaseScraper):
    """네이버 포스트 스크래퍼"""
    def __init__(self):
        self.logger = get_logger()
        self.last_fetch_stats = {}

    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url", "").strip()
        limit = site_config.get("limit", 5)
        self.last_fetch_stats = {"skipped": 0}

        articles = []
        try:
            # 네이버 포스트 작성자 페이지
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")


            # 글 링크 추출
            post_links = soup.select("a.spot_post_area, a.link_end, ul.lst_feed li a")
            if not post_links:
                # 대체 셀렉터
                post_links = soup.select("a[href*='viewer/postView']")

            seen_urls = set()
            for link in post_links:
                if len(articles) >= limit:
                    break
                href = link.get("href", "")
                if "viewer/postView" not in href and "nhn" not in href:
                    continue
                if not href.startswith("http"):
                    href = "https://post.naver.com" + href
                if href in seen_urls:
                    continue
                seen_urls.add(href)

                title_el = link.select_one(".tit_feed, .ell, .tit")
                title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)[:60]
                if not title:
                    continue

                content = self._fetch_post_content(href, site_config)
                if content:
                    articles.append({"title": title, "content": content, "url": href})
                else:
                    self.last_fetch_stats["skipped"] = self.last_fetch_stats.get("skipped", 0) + 1

        except Exception as e:
            self.logger.error(f"네이버 포스트 글 목록 수집 실패: {e}")

        return articles

    def _fetch_post_content(self, post_url: str, site_config: dict) -> str | None:
        """개별 포스트 본문 수집"""
        try:
            resp = requests.get(post_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")


            container = (
                soup.select_one("div.__viewer_container")
                or soup.select_one("div.se_component_wrap")
                or soup.select_one("div.post_ct")
                or soup.select_one("div#cont")
                or soup.select_one("article")
            )
            if not container:
                self.logger.warning(f"포스트 본문 컨테이너 미발견: {post_url}")
                return None

            maybe_strip_images(container, site_config)
            clean_naver_content(container)
            return str(container)

        except Exception as e:
            self.logger.warning(f"포스트 본문 수집 실패 ({post_url}): {e}")
            return None
