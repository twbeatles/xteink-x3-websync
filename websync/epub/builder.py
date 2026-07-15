import os
import io
import html
from datetime import datetime
from ebooklib import epub
from bs4 import BeautifulSoup
from websync.core.logger import get_logger

class EpubBuilder:
    """수집된 기사 데이터를 받아 EPUB 파일로 빌드하는 역할을 전담하는 클래스"""
    def __init__(self, output_dir: str = "./output", font_family: str = "serif", font_size: int = 16, line_height: float = 1.7,
                 epub_theme: str = "default", epub_custom_css: str = ""):
        self.logger = get_logger()
        self.output_dir = output_dir

        self.font_family = font_family
        self.font_size = font_size
        self.line_height = line_height
        self.epub_theme = epub_theme
        self.epub_custom_css = epub_custom_css


    def _load_theme_css(self) -> str:
        """테마 설정에 따라 CSS를 로딩합니다."""
        import sys
        css_text = ""
        
        if self.epub_theme == "custom" and self.epub_custom_css:
            try:
                with open(self.epub_custom_css, "r", encoding="utf-8") as f:
                    css_text = f.read()
            except Exception as e:
                self.logger.warning(f"커스텀 CSS 파일 로드 실패 ({self.epub_custom_css}): {e}")
        elif self.epub_theme != "default":
            if getattr(sys, "frozen", False):
                if hasattr(sys, "_MEIPASS"):
                    base = os.path.join(sys._MEIPASS, "websync", "epub", "themes")
                else:
                    base = os.path.join(os.path.dirname(sys.executable), "epub", "themes")
            else:
                base = os.path.join(os.path.dirname(os.path.abspath(__file__)), "themes")
            theme_path = os.path.join(base, f"{self.epub_theme}.css")
            try:
                with open(theme_path, "r", encoding="utf-8") as f:
                    css_text = f.read()
            except Exception as e:
                self.logger.warning(f"프리셋 테마 CSS 파일 로드 실패 ({theme_path}): {e}")

        
        if css_text:
            css_text = css_text.replace("{{font_family}}", self.font_family)
            css_text = css_text.replace("{{font_size}}", str(self.font_size))
            css_text = css_text.replace("{{line_height}}", str(self.line_height))
            return css_text
        
        return ""

    def _build_default_css(self) -> str:
        """기본 CSS를 생성합니다 (검증된 값 사용)."""
        safe_font = "".join(
            c for c in str(self.font_family or "serif") if c.isalnum() or c in (" ", "-", "_", ",", "'")
        ).strip() or "serif"
        try:
            safe_size = max(8, min(48, int(self.font_size)))
        except (TypeError, ValueError):
            safe_size = 16
        try:
            safe_lh = max(1.0, min(3.0, float(self.line_height)))
        except (TypeError, ValueError):
            safe_lh = 1.7

        return f"""
        body {{
            font-family: {safe_font}, serif, sans-serif;
            padding: 5px;
            line-height: {safe_lh};
            font-size: {safe_size}px;
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
        book.set_identifier(f"x3-websync-{safe_site_name}-{today_str}")

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

        # 테마 CSS 로딩 시도, 실패 시 기본 CSS 생성
        custom_css = self._load_theme_css()
        if not custom_css:
            custom_css = self._build_default_css()


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

    def build_digest(self, articles_by_site: dict[str, list], generate_cover: bool = True) -> str:
        """
        여러 사이트의 기사를 하나의 일간 합본 EPUB으로 빌드합니다.
        
        Args:
            articles_by_site: {사이트명: [기사 dict, ...]} 형식
            generate_cover: 표지 생성 여부
        Returns:
            생성된 epub 파일 경로
        """
        from datetime import date
        from ebooklib import epub
        import html
        
        os.makedirs(self.output_dir, exist_ok=True)
        today = date.today().isoformat()
        
        # 전체 기사 수 계산
        total_articles = sum(len(arts) for arts in articles_by_site.values())
        if total_articles == 0:
            raise ValueError("합본할 기사가 없습니다")
        
        filename = f"Daily_Digest_{today}.epub"
        epub_path = os.path.join(self.output_dir, filename)
        if os.path.exists(epub_path):
            from datetime import datetime
            suffix = datetime.now().strftime("%H%M%S")
            filename = f"Daily_Digest_{today}_{suffix}.epub"
            epub_path = os.path.join(self.output_dir, filename)
        
        book = epub.EpubBook()
        book.set_identifier(f"x3-websync-digest-{today}")
        book.set_title(f"Daily Digest {today}")
        book.set_language("ko")
        book.add_metadata("DC", "description", f"{len(articles_by_site)}개 사이트 {total_articles}개 기사 합본")
        
        # 표지
        if generate_cover:
            cover_data = self._make_cover_image("Daily Digest", total_articles, today)
            if cover_data:
                cover_item = epub.EpubItem(
                    uid="cover-image",
                    file_name="images/cover.jpg",
                    media_type="image/jpeg",
                    content=cover_data
                )
                book.add_item(cover_item)
                book.set_cover("images/cover.jpg", cover_data)
        
        # CSS — build()와 동일한 인라인 <style> 방식 (e-ink 호환성 통일)
        theme_css = self._load_theme_css()
        if not theme_css:
            theme_css = self._build_default_css()

        chapters = []
        toc_sections = []
        chapter_num = 0

        for site_name, articles in articles_by_site.items():
            if not articles:
                continue

            section_chapters = []
            for art in articles:
                chapter_num += 1
                title = art.get("title", f"기사 {chapter_num}")
                safe_title = html.escape(title, quote=True)
                body_html = self._sanitize_body_html(art.get("content", ""))
                summary_html = art.get("summary_html", "")
                summary_block = f'<blockquote class="ai-summary">{summary_html}</blockquote>' if summary_html else ""

                ch = epub.EpubHtml(
                    title=f"[{site_name}] {title}",
                    file_name=f"chapter_{chapter_num:03d}.xhtml",
                    lang="ko"
                )
                ch.content = (
                    '<?xml version="1.0" encoding="utf-8"?>'
                    '<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">'
                    '<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko">'
                    '<head><meta http-equiv="Content-Type" content="application/xhtml+xml; charset=utf-8"/>'
                    f'<title>{safe_title}</title>'
                    f'<style>{theme_css}</style>'
                    '</head><body>'
                    f'<p style="font-size:0.8em;color:#888;">&mdash; {site_name}</p>'
                    f'<h1>{safe_title}</h1>'
                    f'{summary_block}'
                    f'{body_html}'
                    '</body></html>'
                ).encode("utf-8")
                book.add_item(ch)
                chapters.append(ch)
                section_chapters.append(ch)
            
            toc_sections.append((epub.Section(site_name), tuple(section_chapters)))
        
        book.toc = tuple(toc_sections)
        book.add_item(epub.EpubNcx())
        book.add_item(epub.EpubNav())
        book.spine = ["nav"] + chapters
        
        epub.write_epub(epub_path, book)
        return epub_path

