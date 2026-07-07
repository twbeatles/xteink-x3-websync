"""YoutubeScraper"""
from websync.scrapers.base import BaseScraper, HEADERS, maybe_strip_images, extract_rss_link, ensure_article_url
import requests
from bs4 import BeautifulSoup

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
            raise Exception(f"YouTube 채널 수집 실패: {e}") from e
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
