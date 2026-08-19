"""EPUB 본문 정제 — script 외 iframe/이벤트/javascript: 제거."""
from websync.epub.sanitize import sanitize_body_html


def test_sanitize_strips_iframe_and_events():
    html = (
        '<p onclick="alert(1)">본문</p>'
        '<iframe src="https://evil.example"></iframe>'
        '<a href="javascript:alert(2)">링크</a>'
        '<script>evil()</script>'
    )
    out = sanitize_body_html(html)
    assert "<iframe" not in out.lower()
    assert "onclick" not in out.lower()
    assert "javascript:" not in out.lower()
    assert "<script>" not in out.lower()
    assert "본문" in out
    assert "링크" in out
