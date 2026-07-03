"""NaverBlogScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, extract_rss_link, ensure_article_url
import re
import requests
from bs4 import BeautifulSoup

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

                maybe_strip_images(content_elem, site_config)

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
