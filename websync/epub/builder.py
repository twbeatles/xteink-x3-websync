import os
import io
import html
from datetime import datetime
from ebooklib import epub
from bs4 import BeautifulSoup

class EpubBuilder:
    """수집된 기사 데이터를 받아 EPUB 파일로 빌드하는 역할을 전담하는 클래스"""
    def __init__(self, output_dir: str = "./output", font_family: str = "serif", font_size: int = 16, line_height: float = 1.7):
        self.output_dir = output_dir
        self.font_family = font_family
        self.font_size = font_size
        self.line_height = line_height

    @staticmethod
    def _sanitize_body_html(content: str) -> str:
        """본문 HTML에서 script/style 제거 후 반환합니다."""
        if not content:
            return ""
        soup = BeautifulSoup(content, "html.parser")
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        return str(soup)

    def _make_cover_image(self, site_name: str, article_count: int, today_str: str) -> bytes | None:
        """Pillow를 사용해 EPUB 표지 이미지를 동적으로 생성. Pillow 미설치 시 None 반환."""
        try:
            from PIL import Image, ImageDraw, ImageFont
            import textwrap

            W, H = 600, 800
            img = Image.new("RGB", (W, H), color="#1e1e2e")
            draw = ImageDraw.Draw(img)

            for y in range(H):
                ratio = y / H
                r = int(0x1e + (0x31 - 0x1e) * ratio)
                g = int(0x1e + (0x32 - 0x1e) * ratio)
                b = int(0x2e + (0x44 - 0x2e) * ratio)
                draw.line([(0, y), (W, y)], fill=(r, g, b))

            try:
                font_title = ImageFont.truetype("malgunbd.ttf", 48)
                font_sub   = ImageFont.truetype("malgun.ttf", 28)
                font_small = ImageFont.truetype("malgun.ttf", 22)
            except Exception:
                font_title = ImageFont.load_default()
                font_sub   = font_title
                font_small = font_title

            draw.rectangle([40, 80, W - 40, 85], fill="#89b4fa")
            wrapped = textwrap.fill(site_name, width=12)
            draw.multiline_text((W // 2, 160), wrapped, font=font_title, fill="#cdd6f4", anchor="mm", align="center")
            draw.text((W // 2, H // 2 - 20), today_str, font=font_sub, fill="#89b4fa", anchor="mm")
            draw.text((W // 2, H // 2 + 40), f"기사 {article_count}건", font=font_small, fill="#a6e3a1", anchor="mm")
            draw.rectangle([40, H - 85, W - 40, H - 80], fill="#89b4fa")
            draw.text((W // 2, H - 55), "X3 WebSync", font=font_small, fill="#585b70", anchor="mm")

            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
        except ImportError:
            return None
        except Exception:
            return None

    def build(self, site_name: str, articles: list, generate_cover: bool = True) -> str:
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        today_str = datetime.now().strftime("%Y-%m-%d")
        safe_site_name = "".join([c for c in site_name if c.isalnum() or c in (' ', '_', '-')]).strip()
        safe_site_name = safe_site_name.replace(" ", "_")
        file_name = f"{safe_site_name}_{today_str}.epub"
        file_path = os.path.join(self.output_dir, file_name)

        if os.path.exists(file_path):
            time_suffix = datetime.now().strftime("%H%M%S")
            file_name = f"{safe_site_name}_{today_str}_{time_suffix}.epub"
            file_path = os.path.join(self.output_dir, file_name)

        book = epub.EpubBook()
        book.set_title(f"{site_name} ({today_str})")
        book.set_language("ko")

        if generate_cover:
            cover_bytes = self._make_cover_image(site_name, len(articles), today_str)
            if cover_bytes:
                cover_item = epub.EpubItem(
                    uid="cover-image",
                    file_name="images/cover.jpg",
                    media_type="image/jpeg",
                    content=cover_bytes
                )
                book.add_item(cover_item)
                book.set_cover("images/cover.jpg", cover_bytes)

        spine = ["nav"]
        toc = []

        custom_css = f"""
        body {{
            font-family: {self.font_family}, serif, sans-serif;
            padding: 5px;
            line-height: {self.line_height};
            font-size: {self.font_size}px;
            color: #000000;
            background-color: #ffffff;
            text-align: justify;
        }}
        h1 {{
            font-size: 1.35em;
            font-weight: bold;
            border-bottom: 2px solid #555555;
            padding-bottom: 6px;
            margin-top: 15px;
            margin-bottom: 15px;
        }}
        p {{
            margin-top: 0;
            margin-bottom: 0.9em;
            text-indent: 0.5em;
        }}
        blockquote.ai-summary {{
            border-left: 3px solid #555555;
            margin: 10px 5px;
            padding: 8px 12px;
            background-color: #f5f5f5;
            font-style: italic;
            font-size: 0.9em;
        }}
        """

        for idx, art in enumerate(articles):
            safe_title = html.escape(art.get("title", ""), quote=True)
            summary_html = art.get("summary_html", "")
            body_html = self._sanitize_body_html(art.get("content", ""))

            chapter = epub.EpubHtml(
                title=art.get("title", f"Chapter {idx+1}"),
                file_name=f"chap_{idx+1}.xhtml",
                lang="ko"
            )
            chapter.content = f"""
            <?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko">
            <head>
                <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=utf-8" />
                <title>{safe_title}</title>
                <style>
                    {custom_css}
                </style>
            </head>
            <body>
                <h1>{safe_title}</h1>
                {summary_html}
                {body_html}
            </body>
            </html>
            """
            book.add_item(chapter)
            toc.append(chapter)
            spine.append(chapter)

        book.toc = tuple(toc)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = spine

        epub.write_epub(file_path, book)
        return file_path
