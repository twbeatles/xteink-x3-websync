import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup

class BaseScraper(ABC):
    """모든 스크래퍼가 상속받아야 하는 추상 기본 클래스"""
    @abstractmethod
    def fetch_articles(self, site_config: dict) -> list:
        """
        웹 사이트 또는 소스로부터 글 목록을 추출하여 반환합니다.
        반환 형식: [{"title": "제목", "content": "HTML 본문"}]
        """
        pass

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

        # 한글 인코딩 깨짐을 사전에 예방하기 위해 requests의 인코딩을 적절히 설정
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
                
                # 지정된 본문 불필요 요소 제거 필터 적용 (decompose)
                if remove_selectors:
                    selectors = [s.strip() for s in remove_selectors.split(",") if s.strip()]
                    for sel in selectors:
                        for match in content_elem.select(sel):
                            match.decompose()

                # 가독성을 높이기 위해 이미지 태그 삭제 (소형 e-ink 디바이스 최적화)
                for img in content_elem.find_all("img"):
                    img.decompose()
                
                content_html = str(content_elem)
                articles.append({"title": title, "content": content_html})
            except Exception as e:
                print(f"⚠️ 글 수집 중 세부 오류 패스: {e}")
                continue

        return articles

class RssScraper(BaseScraper):
    """RSS 피드 XML을 파싱하여 글 목록을 수집하는 클래스"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url")
        limit = site_config.get("limit", 5)

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }
        
        try:
            response = requests.get(url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"RSS XML 다운로드 실패: {e}")

        # XML 파싱 진행
        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")[:limit]
        if not items:
            items = soup.find_all("entry")[:limit]  # Atom 피드 포맷 지원

        if not items:
            raise Exception("XML 내에서 item 또는 entry 요소를 찾을 수 없습니다.")

        articles = []
        for item in items:
            try:
                title_elem = item.find("title")
                content_elem = item.find("description") or item.find("content") or item.find("summary")
                
                if not title_elem:
                    continue
                
                title = title_elem.text.strip()
                content = content_elem.text.strip() if content_elem else "본문 내용이 없습니다."
                
                # HTML 정리 (이미지 제거)
                content_soup = BeautifulSoup(content, "html.parser")
                for img in content_soup.find_all("img"):
                    img.decompose()
                
                articles.append({"title": title, "content": str(content_soup)})
            except Exception as e:
                print(f"⚠️ RSS 아이템 분석 중 오류 패스: {e}")
                continue

        return articles

class ScraperFactory:
    """스크래퍼 객체 생성을 담당하는 팩토리 클래스 (OCP 준수)"""
    _scrapers = {
        "css": CssSelectorScraper(),
        "rss": RssScraper()
    }

    @classmethod
    def get_scraper(cls, scraper_type: str) -> BaseScraper:
        scraper = cls._scrapers.get(scraper_type.lower())
        if not scraper:
            raise ValueError(f"지원하지 않는 스크래퍼 타입: {scraper_type}")
        return scraper

    @classmethod
    def register_scraper(cls, scraper_type: str, scraper: BaseScraper):
        """향후 새로운 타입의 스크래퍼를 런타임에 동적 등록 가능"""
        cls._scrapers[scraper_type.lower()] = scraper
