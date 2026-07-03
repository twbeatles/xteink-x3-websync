"""CssSelectorScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, extract_rss_link, ensure_article_url
from urllib.parse import urljoin
import requests
from bs4 import BeautifulSoup

class CssSelectorScraper(BaseScraper):
    """일반적인 HTML 구조에서 CSS 선택자(CSS Selector)를 이용해 스크래핑하는 클래스"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url")
        item_selector = site_config.get("item_selector", ".post-item")
        title_selector = site_config.get("title_selector", ".post-title")
        content_selector = site_config.get("content_selector", ".post-content")
        remove_selectors = site_config.get("remove_selectors", "")
        limit = site_config.get("limit", 5)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"HTTP 접속 실패: {e}")

        if response.encoding == 'ISO-8859-1':
            response.encoding = response.apparent_encoding

        soup = BeautifulSoup(response.text, "html.parser")
        posts = soup.select(item_selector)[:limit]
        
        if not posts:
            raise Exception("아이템 선택자(Item Selector)에 매칭되는 요소를 찾지 못했습니다.")

        articles = []
        for idx, post in enumerate(posts):
            try:
                title_elem = post.select_one(title_selector)
                content_elem = post.select_one(content_selector)
                
                if not title_elem:
                    print(f"⚠️ {idx+1}번째 글 제목 요소를 찾지 못했습니다. 건너뜁니다.")
                    continue
                if not content_elem:
                    print(f"⚠️ {idx+1}번째 글 본문 요소를 찾지 못했습니다. 건너뜁니다.")
                    continue
                
                title = title_elem.text.strip()
                
                # 링크 추출
                link_elem = post.select_one("a[href]")
                art_url = url
                if link_elem:
                    href = link_elem["href"]
                    art_url = href if href.startswith("http") else urljoin(url, href)

                # 지정된 본문 불필요 요소 제거 필터 적용 (decompose)
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
                print(f"⚠️ 글 수집 중 세부 오류 패스: {e}")
                continue

        return articles
