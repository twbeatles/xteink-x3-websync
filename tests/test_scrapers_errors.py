from unittest.mock import patch, MagicMock

import pytest

from websync.scrapers.youtube import YoutubeScraper
from websync.scrapers.tistory import TistoryScraper
from websync.scrapers.brunch import BrunchScraper
from websync.scrapers.substack import SubstackScraper


@pytest.mark.parametrize(
    "scraper_cls,site_config",
    [
        (YoutubeScraper, {"url": "https://youtube.com/feeds/videos.xml?channel_id=x", "limit": 1}),
        (TistoryScraper, {"url": "https://example.tistory.com", "limit": 1}),
        (BrunchScraper, {"url": "https://brunch.co.kr/@author", "limit": 1}),
        (SubstackScraper, {"url": "https://example.substack.com", "limit": 1}),
    ],
)
def test_scraper_raises_on_network_failure(scraper_cls, site_config):
    scraper = scraper_cls()
    with patch("requests.get", side_effect=ConnectionError("offline")):
        with pytest.raises(Exception):
            scraper.fetch_articles(site_config)