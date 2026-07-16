import pytest
from websync.scrapers.factory import ScraperFactory


def test_get_scraper_known_types():
    for t in ("css", "rss", "naver", "tistory", "brunch", "youtube", "substack", "soonsal"):
        scraper = ScraperFactory.get_scraper(t)
        assert scraper is not None


def test_get_scraper_unknown_raises():
    with pytest.raises(ValueError, match="지원하지 않는"):
        ScraperFactory.get_scraper("unknown_type")