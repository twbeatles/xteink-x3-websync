import os
from datetime import datetime
from ebooklib import epub

class EpubBuilder:
    """수집된 기사 데이터를 받아 EPUB 파일로 빌드하는 역할을 전담하는 클래스"""
    def __init__(self, output_dir: str = "./output", font_family: str = "serif", font_size: int = 16, line_height: float = 1.7):
        self.output_dir = output_dir
        self.font_family = font_family
        self.font_size = font_size
        self.line_height = line_height

    def build(self, site_name: str, articles: list) -> str:
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir)

        today_str = datetime.now().strftime("%Y-%m-%d")
        safe_site_name = "".join([c for c in site_name if c.isalnum() or c in (' ', '_', '-')]).strip()
        safe_site_name = safe_site_name.replace(" ", "_")
        file_name = f"{safe_site_name}_{today_str}.epub"
        file_path = os.path.join(self.output_dir, file_name)

        book = epub.EpubBook()
        book.set_title(f"{site_name} ({today_str})")
        # 한국어 텍스트 메타데이터 완벽 적용
        book.set_language("ko")

        spine = ["nav"]
        toc = []

        # 한국어 폰트 및 가독성을 극대화한 e-ink 맞춤형 CSS 정의
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
        """

        for idx, art in enumerate(articles):
            chapter = epub.EpubHtml(
                title=art["title"],
                file_name=f"chap_{idx+1}.xhtml",
                lang="ko"
            )
            # 메타태그에 UTF-8 인코딩 선언 명시하여 한글 깨짐 방지
            chapter.content = f"""
            <?xml version="1.0" encoding="utf-8"?>
            <!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.1//EN" "http://www.w3.org/TR/xhtml11/DTD/xhtml11.dtd">
            <html xmlns="http://www.w3.org/1999/xhtml" xml:lang="ko">
            <head>
                <meta http-equiv="Content-Type" content="application/xhtml+xml; charset=utf-8" />
                <title>{art['title']}</title>
                <style>
                    {custom_css}
                </style>
            </head>
            <body>
                <h1>{art['title']}</h1>
                {art['content']}
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
