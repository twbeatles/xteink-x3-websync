import re
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from urllib.parse import urljoin

class BaseScraper(ABC):
    """모든 스크래퍼가 상속받아야 하는 추상 기본 클래스"""
    @abstractmethod
    def fetch_articles(self, site_config: dict) -> list:
        """
        웹 사이트 또는 소스로부터 글 목록을 추출하여 반환합니다.
        반환 형식: [{"title": "제목", "content": "HTML 본문", "url": "고유링크"}]
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

                # 가독성을 높이기 위해 이미지 태그 삭제 (소형 e-ink 디바이스 최적화)
                for img in content_elem.find_all("img"):
                    img.decompose()
                
                content_html = str(content_elem)
                articles.append({"title": title, "content": content_html, "url": art_url})
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
                art_url = link_elem.text.strip() if link_elem else ""

                # HTML 정리 (이미지 제거)
                content_soup = BeautifulSoup(content, "html.parser")
                for img in content_soup.find_all("img"):
                    img.decompose()
                
                articles.append({"title": title, "content": str(content_soup), "url": art_url})
            except Exception as e:
                print(f"⚠️ RSS 아이템 분석 중 오류 패스: {e}")
                continue

        return articles

class NaverBlogScraper(BaseScraper):
    """네이버 블로그를 iframe 우회 및 RSS 피드를 활용해 깔끔하게 크롤링하는 클래스"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url")
        limit = site_config.get("limit", 5)

        # 블로그 ID 추출 (예: https://blog.naver.com/ranto28 -> ranto28)
        match = re.search(r"blog\.naver\.com/([a-zA-Z0-9_\-]+)", url)
        if not match:
            raise Exception("올바른 네이버 블로그 URL 형식이 아닙니다. (예: https://blog.naver.com/아이디)")
        blog_id = match.group(1)

        # 네이버 블로그 RSS 피드 URL 구성
        rss_url = f"https://rss.blog.naver.com/{blog_id}.xml"
        
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        try:
            # RSS 조회하여 최신 글 고유 링크 획득
            response = requests.get(rss_url, headers=headers, timeout=15)
            response.raise_for_status()
        except Exception as e:
            raise Exception(f"네이버 블로그 RSS 호출 실패: {e}")

        soup = BeautifulSoup(response.text, "xml")
        items = soup.find_all("item")[:limit]

        if not items:
            raise Exception("네이버 블로그 RSS에서 포스트 목록을 읽어오지 못했습니다.")

        articles = []
        for item in items:
            try:
                title_elem = item.find("title")
                link_elem = item.find("link")
                if not title_elem or not link_elem:
                    continue

                title = title_elem.text.strip()
                post_link = link_elem.text.strip()

                # 포스트 고유 번호(logNo) 추출 (쿼리 스트링 제거 후 파싱)
                clean_link = post_link.split("?")[0]
                log_no_match = re.search(r"/(\d+)$", clean_link)
                if not log_no_match:
                    log_no_match = re.search(r"logNo=(\d+)", post_link)
                
                if not log_no_match:
                    print(f"⚠️ 네이버 블로그 포스트 번호 파싱 불가로 건너뜀: {post_link}")
                    continue

                log_no = log_no_match.group(1)
                
                # iframe 우회용 실제 본문 주소 호출
                post_view_url = f"https://blog.naver.com/PostView.naver?blogId={blog_id}&logNo={log_no}"
                
                post_response = requests.get(post_view_url, headers=headers, timeout=15)
                if post_response.status_code != 200:
                    print(f"❌ 포스트 본문 획득 실패 (HTTP {post_response.status_code}): {title}")
                    continue

                # 인코딩 처리
                post_response.encoding = post_response.apparent_encoding
                post_soup = BeautifulSoup(post_response.text, "html.parser")

                # SmartEditor One 본문 또는 구버전 포스팅 본문 컨테이너 식별
                content_elem = post_soup.select_one("div.se-main-container") or post_soup.select_one("#postViewArea")
                
                if not content_elem:
                    print(f"⚠️ 본문 엘리먼트를 식별할 수 없습니다. 건너뜁니다: {title}")
                    continue

                # 네이버 블로그 고유 불필요 요소 제거 (신고버튼, 하단 태그버튼 영역 등)
                naver_removes = [
                    ".se-report", ".post-btn", ".se-author-image", 
                    ".se-blog-post-like-and-comment", ".addon", "#naverBlogLikeAndComment"
                ]
                for r_sel in naver_removes:
                    for match_node in content_elem.select(r_sel):
                        match_node.decompose()

                # 가독성을 높이기 위해 이미지 제거 (e-ink 가독 최적화)
                for img in content_elem.find_all("img"):
                    img.decompose()

                # 텍스트 가독성 최적화를 위해 불필요 빈 줄 div 등 가독 패치
                content_html = str(content_elem)
                
                articles.append({
                    "title": title,
                    "content": content_html,
                    "url": post_link
                })
            except Exception as e:
                print(f"⚠️ 네이버 개별 글 파싱 오류 패스: {e}")
                continue

        return articles

class ScraperFactory:
    """스크래퍼 객체 생성을 담당하는 팩토리 클래스 (OCP 준수)"""
    _scrapers = {
        "css": CssSelectorScraper(),
        "rss": RssScraper(),
        "naver": NaverBlogScraper()
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

