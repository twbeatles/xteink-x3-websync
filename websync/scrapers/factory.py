"""스크래퍼 팩토리"""
from websync.scrapers.base import BaseScraper
from websync.scrapers.css import CssSelectorScraper
from websync.scrapers.rss import RssScraper
from websync.scrapers.naver import NaverBlogScraper
from websync.scrapers.tistory import TistoryScraper
from websync.scrapers.brunch import BrunchScraper
from websync.scrapers.youtube import YoutubeScraper
from websync.scrapers.substack import SubstackScraper


class ScraperFactory:
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
        cls._scrapers[scraper_type.lower()] = scraper
