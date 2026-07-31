import pytest
from websync.scrapers.base import _session, fetch_url


def test_base_scraper_session_pool_size():
    # _session의 HTTPAdapter 커넥션 풀 크기가 20 이상으로 설정되었는지 검증
    adapters = _session.adapters
    http_adapter = adapters.get("http://")
    https_adapter = adapters.get("https://")

    assert http_adapter is not None
    assert https_adapter is not None

    assert http_adapter._pool_connections >= 20
    assert http_adapter._pool_maxsize >= 20

    assert https_adapter._pool_connections >= 20
    assert https_adapter._pool_maxsize >= 20
