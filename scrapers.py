import re
import requests
from abc import ABC, abstractmethod
from bs4 import BeautifulSoup
from urllib.parse import urljoin

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

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

        # 블로그 ID 추출 (다양한 네이버 주소 유형 지원: m.blog.naver.com, blog.naver.com, ID.blog.me)
        blog_id = None
        
        # 1. 일반 및 모바일 도메인 매칭 (blog.naver.com/ID 또는 m.blog.naver.com/ID)
        naver_match = re.search(r"blog\.naver\.com/([a-zA-Z0-9_\-]+)", url)
        if naver_match:
            blog_id = naver_match.group(1)
        else:
            # 2. 구형/개인 도메인 매칭 (ID.blog.me)
            me_match = re.search(r"([a-zA-Z0-9_\-]+)\.blog\.me", url)
            if me_match:
                blog_id = me_match.group(1)
                
        if not blog_id:
            raise Exception("올바른 네이버 블로그 URL 형식이 아닙니다. (예: https://blog.naver.com/아이디 또는 https://아이디.blog.me)")

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

                # 모든 하위 태그에 대해 인라인 style 및 class 속성 강제 삭제 (글자 배경색/강조색 제거 및 텍스트화 최적화)
                for tag in content_elem.find_all(True):
                    if tag.has_attr("style"):
                        del tag["style"]
                    if tag.has_attr("class"):
                        del tag["class"]

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

class TistoryScraper(BaseScraper):
    """티스토리 블로그 전용 스크래퍼 - RSS에서 URL 추출 후 본문 직접 수집"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url", "")
        limit = site_config.get("limit", 5)
        articles = []
        try:
            # RSS 피드에서 글 목록 수집
            rss_url = url if url.endswith("/rss") else url.rstrip("/") + "/rss"
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml-xml")
            items = soup.find_all("item")[:limit]
            for item in items:
                title_tag = item.find("title")
                link_tag = item.find("link")
                if not title_tag or not link_tag:
                    continue
                title = title_tag.get_text(strip=True)
                post_url = link_tag.get_text(strip=True) if link_tag else ""
                if not post_url:
                    link_tag2 = item.find("link")
                    post_url = str(link_tag2) if link_tag2 else ""
                content = self._fetch_post_content(post_url)
                if content:
                    articles.append({"title": title, "content": content, "url": post_url})
        except Exception as e:
            print(f"❌ TistoryScraper 오류: {e}")
        return articles

    def _fetch_post_content(self, url: str) -> str:
        if not url:
            return ""
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            # 티스토리 본문 컨테이너 순서대로 탐색
            content_tag = (
                soup.find("div", class_="tt_article_useless_p_margin") or
                soup.find("div", class_="article-view") or
                soup.find("div", id="content") or
                soup.find("article")
            )
            if not content_tag:
                return ""
            # 서식 박멸
            for tag in content_tag.find_all(True):
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("href", "src")}
            for img in content_tag.find_all("img"):
                img.decompose()
            return str(content_tag)
        except Exception as e:
            print(f"⚠️ TistoryScraper 포스트 수집 실패 ({url}): {e}")
            return ""


class BrunchScraper(BaseScraper):
    """카카오 브런치 전용 스크래퍼"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url", "")  # 예: https://brunch.co.kr/@authorid
        limit = site_config.get("limit", 5)
        articles = []
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            # 최신 글 링크 수집
            links = soup.select("a.link_post")[:limit]
            if not links:
                links = soup.select("ul.list_article_m li a")[:limit]
            for a_tag in links:
                href = a_tag.get("href", "")
                if not href:
                    continue
                if not href.startswith("http"):
                    href = "https://brunch.co.kr" + href
                title_tag = a_tag.find("strong") or a_tag.find("h3") or a_tag.find("h4")
                title = title_tag.get_text(strip=True) if title_tag else a_tag.get_text(strip=True)
                content = self._fetch_brunch_content(href)
                if content:
                    articles.append({"title": title, "content": content, "url": href})
        except Exception as e:
            print(f"❌ BrunchScraper 오류: {e}")
        return articles

    def _fetch_brunch_content(self, url: str) -> str:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml")
            content_tag = (
                soup.find("div", class_="wrap_article_body") or
                soup.find("div", class_="article_body") or
                soup.find("article")
            )
            if not content_tag:
                return ""
            # 서식 박멸 + 이미지 제거
            for tag in content_tag.find_all(True):
                tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("href",)}
            for img in content_tag.find_all("img"):
                img.decompose()
            return str(content_tag)
        except Exception as e:
            print(f"⚠️ BrunchScraper 포스트 수집 실패 ({url}): {e}")
            return ""


class YoutubeScraper(BaseScraper):
    """YouTube 채널 최신 영상의 자막을 수집하여 EPUB으로 변환하는 스크래퍼"""
    def fetch_articles(self, site_config: dict) -> list:
        # url은 채널 RSS 피드: https://www.youtube.com/feeds/videos.xml?channel_id=...
        url = site_config.get("url", "")
        limit = site_config.get("limit", 3)
        articles = []
        try:
            resp = requests.get(url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml-xml")
            entries = soup.find_all("entry")[:limit]
            for entry in entries:
                title_tag = entry.find("title")
                video_id_tag = entry.find("yt:videoId")
                if not title_tag or not video_id_tag:
                    continue
                title = title_tag.get_text(strip=True)
                video_id = video_id_tag.get_text(strip=True)
                video_url = f"https://www.youtube.com/watch?v={video_id}"
                content = self._fetch_transcript(video_id, title)
                if content:
                    articles.append({"title": title, "content": content, "url": video_url})
        except Exception as e:
            print(f"❌ YoutubeScraper 오류: {e}")
        return articles

    def _fetch_transcript(self, video_id: str, title: str) -> str:
        try:
            from youtube_transcript_api import YouTubeTranscriptApi, NoTranscriptFound, TranscriptsDisabled
            # 한국어 자막 우선, 없으면 자동생성 한국어, 없으면 영어
            for lang in (["ko"], ["en"]):
                try:
                    transcript = YouTubeTranscriptApi.get_transcript(video_id, languages=lang)
                    # 문장 단위 단락 구성
                    paragraphs = []
                    chunk = []
                    for seg in transcript:
                        chunk.append(seg["text"])
                        if len(chunk) >= 10:
                            paragraphs.append("<p>" + " ".join(chunk) + "</p>")
                            chunk = []
                    if chunk:
                        paragraphs.append("<p>" + " ".join(chunk) + "</p>")
                    return "\n".join(paragraphs)
                except (NoTranscriptFound, Exception):
                    continue
        except ImportError:
            print("⚠️ youtube_transcript_api 미설치. pip install youtube-transcript-api")
        except Exception as e:
            print(f"⚠️ YouTube 자막 수집 실패 ({video_id}): {e}")
        return ""


class SubstackScraper(BaseScraper):
    """Substack 뉴스레터 전용 스크래퍼 - RSS 전문을 수신 후 Substack 고유 요소 클렌징"""
    def fetch_articles(self, site_config: dict) -> list:
        url = site_config.get("url", "")  # 예: https://example.substack.com/feed
        limit = site_config.get("limit", 5)
        articles = []
        try:
            rss_url = url if "/feed" in url else url.rstrip("/") + "/feed"
            resp = requests.get(rss_url, headers=HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "lxml-xml")
            items = soup.find_all("item")[:limit]
            for item in items:
                title_tag = item.find("title")
                link_tag = item.find("link")
                desc_tag = item.find("content:encoded") or item.find("description")
                if not title_tag:
                    continue
                title = title_tag.get_text(strip=True)
                link = link_tag.get_text(strip=True) if link_tag else ""
                content_html = desc_tag.get_text() if desc_tag else ""
                # Substack 특유의 paywall/버튼 클렌징
                content_soup = BeautifulSoup(content_html, "lxml")
                for sel in ["div.subscribe-widget", "div.paywall", "div.button-wrapper", ".post-footer"]:
                    for el in content_soup.select(sel):
                        el.decompose()
                for tag in content_soup.find_all(True):
                    tag.attrs = {k: v for k, v in tag.attrs.items() if k in ("href",)}
                for img in content_soup.find_all("img"):
                    img.decompose()
                clean_content = str(content_soup)
                articles.append({"title": title, "content": clean_content, "url": link})
        except Exception as e:
            print(f"❌ SubstackScraper 오류: {e}")
        return articles


class ScraperFactory:
    """스크래퍼 객체 생성을 담당하는 팩토리 클래스 (OCP 준수)"""
    _scrapers = {
        "css": CssSelectorScraper(),
        "rss": RssScraper(),
        "naver": NaverBlogScraper(),
        "tistory": TistoryScraper(),
        "brunch": BrunchScraper(),
        "youtube": YoutubeScraper(),
        "substack": SubstackScraper(),
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

