"""MoneyLetterScraper — 어피티 머니레터(uppity.co.kr) 전용 스크래퍼

BaseNewsletterScraper를 상속. 목록은 Unlimited Elements 포스트 그리드,
상세는 Elementor 싱글 포스트 본문을 사용한다.

사용 예:
    {
      "name": "머니레터",
      "type": "moneyletter",
      "url": "https://uppity.co.kr/newsletter/money-letter/",
      "limit": 3
    }
"""

from __future__ import annotations

import re
from urllib.parse import unquote, urljoin, urlparse

from bs4 import BeautifulSoup

from websync.scrapers.base import fetch_url
from websync.scrapers.newsletter_base import BaseNewsletterScraper


class MoneyLetterScraper(BaseNewsletterScraper):
    """어피티 머니레터(https://uppity.co.kr/newsletter/money-letter/) 전용 구현.

    - 아카이브: `/newsletter/money-letter/` (+ 페이지네이션 `/2/` 등)
    - 상세: 도메인 루트 단일 슬러그 포스트 (`/💰제목-슬러그/`)
    """

    # 상세 URL 판별·폴백 링크 매칭용 (실제 목록 추출은 _extract_links 오버라이드)
    LINK_PATTERN = re.compile(
        r"(?:https?://(?:www\.)?uppity\.co\.kr)?/[^/\s?#]+/?$",
        re.IGNORECASE,
    )

    ARCHIVE_PATTERN = re.compile(
        r"/newsletter/money-letter/?(?:\d+/?)?$",
        re.IGNORECASE,
    )

    # 목록/사이트 공용 경로 — 기사 슬러그가 아님
    _EXCLUDED_SLUGS = frozenset({
        "newsletter", "category", "tag", "author", "page", "product",
        "shop", "subscription", "wp-admin", "wp-login.php", "wp-content",
        "wp-json", "feed", "cart", "checkout", "my-account", "privacy-policy",
        "about", "contact", "search",
    })

    CONTENT_CANDIDATES = [
        ".elementor-widget-theme-post-content .elementor-widget-container",
        ".elementor-widget-theme-post-content",
        "div.elementor-location-single",
        "div.entry-content",
        "article",
        "main",
        "body",
    ]

    def _is_detail_url(self, url: str) -> bool:
        """아카이브가 아니고 단일 슬러그 포스트이면 상세로 본다."""
        path = urlparse(url).path or ""
        if self.ARCHIVE_PATTERN.search(path):
            return False
        segments = [s for s in path.split("/") if s]
        if len(segments) != 1:
            return False
        slug = unquote(segments[0]).lower()
        if slug in self._EXCLUDED_SLUGS:
            return False
        return True

    def _extract_links(self, soup: BeautifulSoup, base_url: str) -> list[tuple[str, str]]:
        """머니레터 아카이브 포스트 그리드에서 기사 링크를 추출."""
        results: list[tuple[str, str]] = []
        seen: set[str] = set()

        items = soup.select(
            ".ue-item, .uc_post_grid_style_one_item, .ue_post_grid_item"
        )
        if items:
            for item in items:
                pair = self._best_link_from_container(item, base_url)
                if not pair:
                    continue
                full, title = pair
                if full in seen:
                    continue
                seen.add(full)
                results.append((full, title))
            if results:
                return results

        # 그리드 마크업이 바뀐 경우: a 태그 전체에서 상세 URL만 수집
        for a in soup.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            full = urljoin(base_url, href)
            if full in seen or not self._is_detail_url(full):
                continue
            title = a.get_text(strip=True) or "머니레터"
            # 이미지 전용 링크(짧은/빈 텍스트)는 건너뛰고, 같은 URL의 제목 링크를 우선
            if len(title) < 8:
                continue
            seen.add(full)
            results.append((full, title))
        return results

    def _best_link_from_container(
        self, container, base_url: str
    ) -> tuple[str, str] | None:
        """그리드 카드 안에서 제목 텍스트가 가장 긴 상세 링크를 고른다."""
        best: tuple[str, str] | None = None
        best_len = -1
        for a in container.select("a[href]"):
            href = (a.get("href") or "").strip()
            if not href:
                continue
            full = urljoin(base_url, href)
            if not self._is_detail_url(full):
                continue
            text = a.get_text(strip=True) or ""
            score = len(text)
            if score > best_len:
                best_len = score
                best = (full, text or "머니레터")
        return best

    def _get_title(self, url: str) -> str | None:
        """og:title 우선, 없으면 <title>."""
        try:
            resp = fetch_url(url, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            og = soup.select_one('meta[property="og:title"]')
            if og and og.get("content"):
                return og["content"].strip()
            if soup.title and soup.title.string:
                return soup.title.string.strip()
        except Exception:
            pass
        return None

    def _clean_content(self, container: BeautifulSoup, site_config: dict) -> None:
        """머니레터/어피티 특화 정제."""
        super()._clean_content(container, site_config)

        for sel in (
            "form",
            ".elementor-widget-form",
            ".elementor-location-header",
            ".elementor-location-footer",
            ".sharedaddy",
            ".jp-relatedposts",
            ".elementor-widget-share-buttons",
            "[class*='subscribe']",
            "[class*='newsletter-signup']",
            "[class*='related']",
        ):
            for el in container.select(sel):
                el.decompose()

        # 구독 CTA 문구가 들어간 짧은 블록 제거
        for el in list(container.find_all(["div", "section", "p", "a"])):
            txt = el.get_text(strip=True)
            if not txt:
                continue
            if len(txt) < 40 and any(
                kw in txt for kw in ("구독하기", "무료 구독", "뉴스레터 구독", "개인정보 수집")
            ):
                el.decompose()
