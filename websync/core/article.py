"""기사 URL·동기화 키 유틸리티"""

import hashlib


def ensure_article_url(url: str, base_url: str, title: str) -> str:
    """고유 URL이 없으면 base+title 해시 기반 synthetic URL을 생성합니다."""
    url = (url or "").strip()
    if url:
        return url
    title = (title or "").strip()
    if not title:
        return ""
    digest = hashlib.sha256(f"{base_url}:{title}".encode("utf-8")).hexdigest()[:16]
    return f"synckey://{digest}"
