import os
import tempfile
import zipfile

from websync.epub.builder import EpubBuilder


def test_build_creates_epub_with_escaped_title():
    with tempfile.TemporaryDirectory() as tmp:
        builder = EpubBuilder(output_dir=tmp, font_family="serif", font_size=16, line_height=1.5)
        path = builder.build(
            "테스트 사이트",
            [
                {
                    "title": '제목 <script>alert(1)</script>',
                    "content": "<p>본문</p><script>evil()</script>",
                    "url": "https://ex.com/1",
                }
            ],
            generate_cover=False,
        )
        assert os.path.isfile(path)
        assert path.endswith(".epub")
        with zipfile.ZipFile(path, "r") as zf:
            names = zf.namelist()
            assert any(n.endswith(".xhtml") or n.endswith(".html") for n in names)
            # 챕터 내용 확인
            chapter = next(n for n in names if "chap" in n.lower() or n.endswith(".xhtml"))
            data = zf.read(chapter).decode("utf-8", errors="ignore")
            assert "<script>" not in data
            assert "evil()" not in data


def test_build_avoids_overwrite_with_suffix():
    with tempfile.TemporaryDirectory() as tmp:
        builder = EpubBuilder(output_dir=tmp)
        p1 = builder.build("Site", [{"title": "a", "content": "<p>1</p>", "url": "u1"}], generate_cover=False)
        p2 = builder.build("Site", [{"title": "b", "content": "<p>2</p>", "url": "u2"}], generate_cover=False)
        assert p1 != p2
        assert os.path.isfile(p1) and os.path.isfile(p2)
