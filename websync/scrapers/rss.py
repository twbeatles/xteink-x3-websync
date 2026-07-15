"""RssScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, extract_rss_link, ensure_article_url, fetch_url
import re
from bs4 import BeautifulSoup

class RssScraper(BaseScraper):
    """RSS 피드 XML을 파싱하여 글 목록을 수집하는 클래스"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url")
        limit = site_config.get("limit", 5)

        try:
            response = fetch_url(url, timeout=15)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"RSS XML 다운로드 실패: {e}")

        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")[:limit]
        if not items:
            items = soup.find_all("entry")[:limit]

        if not items:
            raise Exception("XML 내에서 item 또는 entry 요소를 찾을 수 없습니다.")

        articles = []
        for item in items:
            try:
                title_elem = item.find("title")
                content_elem = item.find("description") or item.find("content") or item.find("summary")
                link_elem = item.find("link")
                
                if not title_elem:
                    continue
                
                title = title_elem.text.strip()
                content = content_elem.text.strip() if content_elem else "본문 내용이 없습니다."
                art_url = extract_rss_link(item, url)

                content_soup = BeautifulSoup(content, "html.parser")
                maybe_strip_images(content_soup, site_config)
                art_url = ensure_article_url(art_url, url, title)

                articles.append({"title": title, "content": str(content_soup), "url": art_url})
            except Exception as e:
                print(f"⚠️ RSS 아이템 분석 중 오류 패스: {e}")
                continue

        return articles
