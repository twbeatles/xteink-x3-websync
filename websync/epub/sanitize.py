"""EPUB 본문 HTML 정제."""
from __future__ import annotations

from bs4 import BeautifulSoup


def sanitize_body_html(content: str) -> str:
    """본문 HTML에서 script/style 제거 후 반환합니다."""
    if not content:
        return ""
    soup = BeautifulSoup(content, "html.parser")
    for tag in soup.find_all(["script", "style"]):
        tag.decompose()
    return str(soup)
