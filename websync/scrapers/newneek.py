"""NewneekScraper — 뉴닉(newneek.co) 아티클 수집.

목록: sitemap (article-sitemap / news-sitemap)
본문: 상세 페이지 __NEXT_DATA__ 의 layoutData.articleContent
"""
from __future__ import annotations

import json
import re
from urllib.parse import urlparse

from bs4 import BeautifulSoup

from websync.core.logger import get_logger
from websync.scrapers.base import BaseScraper, ensure_article_url, fetch_url, maybe_strip_images


class NewneekScraper(BaseScraper):
    """뉴닉 공개 아티클 스크래퍼."""

    SITEMAP_INDEX = "https://newneek.co/sitemap.xml"
    ARTICLE_SITEMAP = "https://newneek.co/sitemap/article-sitemap.xml"
    NEWS_SITEMAP = "https://newneek.co/sitemap/news-sitemap.xml"
    _ARTICLE_RE = re.compile(
        r"https?://(?:www\.)?newneek\.co/@([\w.-]+)/article/(\d+)", re.I
    )
    _HANDLE_RE = re.compile(r"newneek\.co/@([\w.-]+)", re.I)

    def __init__(self):
        self.logger = get_logger()
        self.last_fetch_stats: dict = {}

    def fetch_articles(self, site_config: dict) -> list:
        self.last_fetch_stats = {"skipped": 0}
        url = (site_config.get("url") or "").strip() or "https://newneek.co/@newneek"
        limit = int(site_config.get("limit", 5) or 5)
        articles: list[dict] = []
        skipped = 0

        # 단일 글
        single = self._ARTICLE_RE.search(url)
        if single and "/article/" in url:
            handle, aid = single.group(1), single.group(2)
            post_url = f"https://newneek.co/@{handle}/article/{aid}"
            title, content = self._fetch_article(post_url, site_config)
            if content:
                articles.append({
                    "title": title or f"뉴닉 {aid}",
                    "content": content,
                    "url": ensure_article_url(post_url, url, title or aid),
                })
            else:
                skipped += 1
            self.last_fetch_stats = {"skipped": skipped}
            if not articles:
                raise Exception("뉴닉 단일 글 본문 수집 실패")
            return articles

        handle = self._extract_handle(url) or "newneek"
        try:
            links = self._list_from_sitemap(handle, limit * 2)
        except Exception as e:
            raise Exception(f"뉴닉 사이트맵 수집 실패: {e}") from e

        if not links:
            raise Exception(f"뉴닉 사이트맵에서 @{handle} 글을 찾지 못했습니다.")

        for post_url in links:
            if len(articles) >= limit:
                break
            title, content = self._fetch_article(post_url, site_config)
            if content:
                articles.append({
                    "title": title or post_url,
                    "content": content,
                    "url": ensure_article_url(post_url, url, title or post_url),
                })
            else:
                skipped += 1

        self.last_fetch_stats = {"skipped": skipped}
        if not articles:
            raise Exception(f"뉴닉 목록 {len(links)}건 중 본문 수집 성공 0건")
        return articles

    def _extract_handle(self, url: str) -> str | None:
        m = self._HANDLE_RE.search(url or "")
        if m:
            return m.group(1)
        path = urlparse(url).path if url else ""
        m2 = re.search(r"/@([\w.-]+)", path)
        return m2.group(1) if m2 else None

    def _list_from_sitemap(self, handle: str, limit: int) -> list[str]:
        """최신 글 URL 목록 (사이트맵 상단이 최신)."""
        # news-sitemap 이 작고 최신 위주 — 우선 시도
        for sm_url in (self.NEWS_SITEMAP, self.ARTICLE_SITEMAP):
            try:
                resp = fetch_url(sm_url, timeout=25)
                resp.raise_for_status()
                text = resp.content.decode("utf-8", errors="replace")
            except Exception as e:
                self.logger.warning(f"사이트맵 조회 실패 ({sm_url}): {e}")
                continue

            urls = re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", text)
            matched = [
                u.strip()
                for u in urls
                if f"/@{handle}/article/" in u
            ]
            if matched:
                return matched[:limit]
        return []

    def _fetch_article(self, post_url: str, site_config: dict) -> tuple[str, str]:
        """(title, content_html). 실패 시 ("", "")."""
        try:
            resp = fetch_url(post_url, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            nd = soup.select_one("script#__NEXT_DATA__")
            title = ""
            html = ""
            if nd and nd.string:
                data = json.loads(nd.string)
                layout = (
                    (data.get("props") or {})
                    .get("pageProps", {})
                    .get("layoutData")
                    or {}
                )
                title = (layout.get("articleTitle") or "").strip()
                html = layout.get("articleContent") or ""
            if not html:
                # 폴백: 본문 후보
                body = (
                    soup.select_one("article")
                    or soup.select_one("main")
                    or soup.select_one("[class*='content']")
                )
                if body:
                    html = str(body)
                if not title and soup.title and soup.title.string:
                    title = soup.title.string.strip()

            if not html:
                return title, ""

            content_soup = BeautifulSoup(html, "lxml")
            container = content_soup.body or content_soup
            for tag_name in ("script", "style", "nav", "footer", "form"):
                for t in container.find_all(tag_name):
                    t.decompose()
            for tag in container.find_all(True):
                tag.attrs = {
                    k: v for k, v in tag.attrs.items() if k in ("href", "src", "alt", "title")
                }
            maybe_strip_images(container, site_config)
            text = container.get_text(" ", strip=True)
            if len(text) < 40:
                return title, ""
            return title, str(container)
        except Exception as e:
            self.logger.warning(f"뉴닉 본문 수집 실패 ({post_url}): {e}")
            return "", ""
