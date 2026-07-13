"""CssSelectorScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, ensure_article_url
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup


class CssSelectorScraper(BaseScraper):
    """일반적인 HTML 구조에서 CSS 선택자(CSS Selector)를 이용해 스크래핑하는 클래스"""

    def __init__(self):
        self.last_fetch_stats: dict = {}

    def fetch_articles(self, site_config: dict) -> list:
        self.last_fetch_stats = {"skipped": 0, "reasons": []}
        url = site_config.get("url")
        item_selector = site_config.get("item_selector", ".post-item")
        title_selector = site_config.get("title_selector", ".post-title")
        content_selector = site_config.get("content_selector", ".post-content")
        remove_selectors = site_config.get("remove_selectors", "")
        limit = site_config.get("limit", 5)
        fetch_detail = bool(site_config.get("fetch_detail_page", False))

        headers = dict(HEADERS)

        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"HTTP 접속 실패: {e}") from e

        if response.encoding == "ISO-8859-1":
            response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select(item_selector)[:limit]

        if not posts:
            raise Exception("아이템 선택자(Item Selector)에 매칭되는 요소를 찾지 못했습니다.")

        articles = []
        skipped = 0
        for idx, post in enumerate(posts):
            try:
                title_elem = post.select_one(title_selector)
                if not title_elem:
                    skipped += 1
                    print(f"⚠️ {idx+1}번째 글 제목 요소를 찾지 못했습니다. 건너뜁니다.")
                    continue

                title = title_elem.text.strip()

                link_elem = post.select_one("a[href]")
                art_url = url
                if link_elem:
                    href = link_elem.get("href", "")
                    if href:
                        art_url = href if href.startswith("http") else urljoin(url, href)

                content_elem = None
                if fetch_detail and art_url and art_url != url:
                    content_elem = self._fetch_detail_content(
                        art_url, content_selector, remove_selectors, site_config, headers
                    )
                    if content_elem is None:
                        skipped += 1
                        print(f"⚠️ 상세 페이지 본문 실패, 목록 본문으로 폴백하지 않고 스킵: {title}")
                        continue
                else:
                    content_elem = post.select_one(content_selector)
                    if not content_elem:
                        skipped += 1
                        print(f"⚠️ {idx+1}번째 글 본문 요소를 찾지 못했습니다. 건너뜁니다.")
                        continue
                    if remove_selectors:
                        selectors = [s.strip() for s in remove_selectors.split(",") if s.strip()]
                        for sel in selectors:
                            for match in content_elem.select(sel):
                                match.decompose()
                    maybe_strip_images(content_elem, site_config)

                content_html = str(content_elem)
                art_url = ensure_article_url(art_url, url, title)
                articles.append({"title": title, "content": content_html, "url": art_url})
            except Exception as e:
                skipped += 1
                print(f"⚠️ 글 수집 중 세부 오류 패스: {e}")
                continue

        self.last_fetch_stats = {"skipped": skipped, "reasons": []}
        if posts and not articles:
            raise Exception(
                f"목록 {len(posts)}건 중 본문 수집 성공 0건 (선택자·상세 페이지 설정을 확인하세요)"
            )
        return articles

    def _fetch_detail_content(
        self,
        art_url: str,
        content_selector: str,
        remove_selectors: str,
        site_config: dict,
        headers: dict,
    ):
        try:
            resp = requests.get(art_url, headers=headers, timeout=15)
            resp.raise_for_status()
            if resp.encoding == "ISO-8859-1":
                resp.encoding = resp.apparent_encoding
            detail = BeautifulSoup(resp.text, "html.parser")
            content_elem = detail.select_one(content_selector)
            if not content_elem:
                return None
            if remove_selectors:
                selectors = [s.strip() for s in remove_selectors.split(",") if s.strip()]
                for sel in selectors:
                    for match in content_elem.select(sel):
                        match.decompose()
            maybe_strip_images(content_elem, site_config)
            return content_elem
        except Exception as e:
            print(f"⚠️ 상세 페이지 수집 실패 ({art_url}): {e}")
            return None
