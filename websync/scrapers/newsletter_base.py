"""뉴스레터(아카이브 목록 + 상세 페이지) 공통 기반

이 모듈은 '일자별/주제별 뉴스레터 아카이브' 형태의 사이트를 위한
재사용 가능한 기반 클래스를 제공합니다.

목적: soonsal 외에 앞으로 추가될 다른 뉴스레터 사이트(예: 다른 브리핑, paid newsletter HTML 등)를
최소 코드로 빠르게 추가할 수 있게 하기 위함.

사용법 (미래 확장 예시):
    from .newsletter_base import BaseNewsletterScraper

    class MyOtherNewsletterScraper(BaseNewsletterScraper):
        LINK_PATTERN = re.compile(r"/archive/\\d{4}/\\d{2}/\\d{2}\\.html")  # 실제 사용 시 r"..." raw string 사용
        CONTENT_CANDIDATES = ["div.post-body", "article.main", "div#content"]

        def _clean_content(self, container: BeautifulSoup, site_config: dict) -> None:
            # 필요시 soonsal과 다른 추가 정제 로직
            super()._clean_content(container, site_config)
            # 예: 특정 광고 div 제거
            for ad in container.select(".promo, .newsletter-signup"):
                ad.decompose()

등록 후 "my_other_newsletter" 타입으로 사용 가능.
"""

import re
from abc import abstractmethod
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from websync.scrapers.base import BaseScraper, fetch_url, maybe_strip_images, ensure_article_url
from websync.core.logger import get_logger


class BaseNewsletterScraper(BaseScraper):
    """뉴스레터 아카이브 스타일 스크래퍼의 공통 기반.

    하위 클래스는 최소한 다음을 정의/오버라이드하면 됩니다:
    - LINK_PATTERN (정규식)
    - CONTENT_CANDIDATES (선택자 리스트)
    - (선택) _is_detail_url, _clean_content, _get_title
    """

    # 하위 클래스에서 반드시 오버라이드
    LINK_PATTERN: re.Pattern = re.compile(r"")  # 예: r"/newsletters/\d{4}/\d{4}(-[a-z]+)?\.html"  (raw string 추천)

    # 상세 페이지 본문 후보 선택자 (크기 + 우선순위 순)
    CONTENT_CANDIDATES: list[str] = ["article", "main", "div.content", "body"]

    def __init__(self):
        self.logger = get_logger()
        self.last_fetch_stats: dict = {}

    def fetch_articles(self, site_config: dict) -> list:
        self.last_fetch_stats = {"skipped": 0}
        url = (site_config.get("url") or "").strip()
        limit = int(site_config.get("limit", 5))
        articles: list[dict] = []
        skipped = 0

        if not url or not self.LINK_PATTERN:
            raise ValueError("URL 또는 LINK_PATTERN이 설정되지 않았습니다.")

        try:
            if self._is_detail_url(url):
                content = self._fetch_and_clean_detail(url, site_config)
                if content:
                    title = self._get_title(url) or "뉴스레터"
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": ensure_article_url(url, url, title)
                    })
                else:
                    skipped += 1
            else:
                resp = fetch_url(url, timeout=15)
                resp.raise_for_status()
                soup = BeautifulSoup(resp.text, "lxml")

                links = self._extract_links(soup, url)[:limit]
                for link_url, link_text in links:
                    content = self._fetch_and_clean_detail(link_url, site_config)
                    if not content:
                        skipped += 1
                        continue
                    title = self._get_title(link_url) or link_text or "뉴스레터"
                    articles.append({
                        "title": title,
                        "content": content,
                        "url": ensure_article_url(link_url, url, title)
                    })

            self.last_fetch_stats = {"skipped": skipped}

            if not articles and (locals().get("links") or self._is_detail_url(url)):
                raise Exception("뉴스레터 본문 수집에 성공한 항목이 없습니다.")

        except Exception as e:
            if "본문 수집" in str(e):
                raise
            raise Exception(f"{self.__class__.__name__} 수집 실패: {e}") from e

        return articles

    # ---------- 오버라이드 가능한 메서드 ----------

    def _is_detail_url(self, url: str) -> bool:
        """이 URL이 단일 뉴스레터 상세 페이지인지 판단. 기본은 LINK_PATTERN 매칭."""
        return bool(self.LINK_PATTERN.search(url))

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
        """아카이브 페이지에서 뉴스레터 상세 링크들을 추출."""
        results: list[tuple[str, str]] = []
        seen = set()

        for a in soup.select('a[href]'):
            href = a.get("href", "").strip()
            if not href or not self.LINK_PATTERN.search(href):
                continue
            full = urljoin(base_url, href)
            if full in seen:
                continue
            seen.add(full)
            title = a.get_text(strip=True) or "뉴스레터"
            results.append((full, title))
        return results

    def _fetch_and_clean_detail(self, url: str, site_config: dict) -> str:
        """상세 페이지를 가져와 본문을 정제."""
        try:
            resp = fetch_url(url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")

            container = self._find_content_container(soup)
            if not container:
                self.logger.warning(f"본문 컨테이너를 찾을 수 없음: {url}")
                return ""

            self._clean_content(container, site_config)
            maybe_strip_images(container, site_config)

            return str(container)
        except Exception as e:
            self.logger.warning(f"상세 페이지 수집 실패 ({url}): {e}")
            return ""

    def _find_content_container(self, soup: BeautifulSoup):
        """CONTENT_CANDIDATES 중 적합한 컨테이너 반환."""
        for sel in self.CONTENT_CANDIDATES:
            el = soup.select_one(sel)
            if el and len(el.get_text(strip=True)) > 150:
                return el
        return soup.body or soup

    def _clean_content(self, container: BeautifulSoup, site_config: dict) -> None:
        """공통 불필요 요소 제거. 하위 클래스에서 추가로 override."""
        for tag_name in ("nav", "header", "footer", "aside", "script", "style", "form", "noscript"):
            for t in container.find_all(tag_name):
                t.decompose()

        # 기본 속성 정리 (필요한 것만)
        for tag in container.find_all(True):
            kept = {k: v for k, v in tag.attrs.items() if k in ("href", "src", "alt", "title")}
            tag.attrs = kept

    def _get_title(self, url: str) -> str | None:
        """상세 페이지에서 제목을 추출 (기본: <title>)."""
        try:
            resp = fetch_url(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            if soup.title and soup.title.string:
                return soup.title.string.strip()
        except Exception:
            pass
        return None
