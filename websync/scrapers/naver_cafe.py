"""네이버 카페 전용 스크래퍼

공개 카페의 최신글/인기글을 수집합니다.
URL 형식: https://cafe.naver.com/{cafe_id}
"""
import re
import requests
from bs4 import BeautifulSoup
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images
from websync.scrapers.naver_common import clean_naver_content
from websync.core.logger import get_logger


class NaverCafeScraper(BaseScraper):
    """네이버 카페 공개 게시판 스크래퍼"""
    def __init__(self):
        self.logger = get_logger()
        self.last_fetch_stats = {}

    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url", "").strip()
        limit = site_config.get("limit", 5)
        self.last_fetch_stats = {"skipped": 0}

        # cafe_id 추출
        match = re.search(r"cafe\.naver\.com/([^/?#]+)", url)
        if not match:
            self.logger.error(f"네이버 카페 URL에서 cafe_id를 추출할 수 없습니다: {url}")
            return []
        cafe_id = match.group(1)

        articles = []
        try:
            # 모바일 페이지 사용 (더 단순한 구조)
            mobile_url = f"https://m.cafe.naver.com/ca-fe/web/cafes/{cafe_id}/articles?page=1&pageSize={limit}"
            resp = requests.get(mobile_url, headers={**HEADERS, "Referer": f"https://m.cafe.naver.com/{cafe_id}"}, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding


            # JSON API 응답 파싱 시도
            try:
                data = resp.json()
                article_list = data.get("message", {}).get("result", {}).get("articleList", [])
                for item in article_list[:limit]:
                    article_id = item.get("articleId")
                    title = item.get("subject", "제목 없음")
                    article_url = f"https://cafe.naver.com/{cafe_id}/{article_id}"
                    content = self._fetch_article_content(cafe_id, article_id, site_config)
                    if content:
                        articles.append({"title": title, "content": content, "url": article_url})
                    else:
                        self.last_fetch_stats["skipped"] = self.last_fetch_stats.get("skipped", 0) + 1
            except (ValueError, KeyError):
                # JSON 파싱 실패 시 HTML 파싱 시도
                soup = BeautifulSoup(resp.text, "html.parser")
                links = soup.select("a.article_item, a.board-list-item, a.ArticleListItem")
                for link in links[:limit]:
                    href = link.get("href", "")
                    title_el = link.select_one(".item_subject, .board-list-item__tit, .article_title")
                    title = title_el.get_text(strip=True) if title_el else link.get_text(strip=True)
                    if not title:
                        continue
                    article_match = re.search(r"/(\d+)$", href)
                    if not article_match:
                        continue
                    article_id = article_match.group(1)
                    article_url = f"https://cafe.naver.com/{cafe_id}/{article_id}"
                    content = self._fetch_article_content(cafe_id, article_id, site_config)
                    if content:
                        articles.append({"title": title, "content": content, "url": article_url})
                    else:
                        self.last_fetch_stats["skipped"] = self.last_fetch_stats.get("skipped", 0) + 1

        except Exception as e:
            self.logger.error(f"네이버 카페 글 목록 수집 실패: {e}")

        return articles

    def _fetch_article_content(self, cafe_id: str, article_id, site_config: dict) -> str | None:
        """개별 카페 게시글 본문 수집"""
        try:
            content_url = f"https://m.cafe.naver.com/ca-fe/web/cafes/{cafe_id}/articles/{article_id}"
            resp = requests.get(content_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding
            soup = BeautifulSoup(resp.text, "html.parser")


            # 본문 컨테이너 다중 후보
            container = (
                soup.select_one("div.se-main-container")
                or soup.select_one("div.article_viewer")
                or soup.select_one("div#postContent")
                or soup.select_one("div.ContentRenderer")
                or soup.select_one("article")
            )
            if not container:
                self.logger.warning(f"카페 게시글 본문 컨테이너 미발견: {article_id}")
                return None

            maybe_strip_images(container, site_config)
            clean_naver_content(container)
            return str(container)

        except Exception as e:
            self.logger.warning(f"카페 게시글 본문 수집 실패 ({article_id}): {e}")
            return None
