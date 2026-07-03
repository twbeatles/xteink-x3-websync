"""OPDS 카탈로그 HTTP 서버"""
import os
import re
import threading
from datetime import datetime
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Optional


class OPDSHandler(BaseHTTPRequestHandler):
    """OPDS XML 카탈로그 및 파일 다운로드를 처리하는 HTTP 핸들러"""
    output_dir: str = "./output"

    def log_message(self, format, *args):
        pass

    def do_GET(self):
        if self.path in ("/", "/opds", "/opds/"):
            self._serve_catalog()
        elif self.path.startswith("/opds/download/"):
            self._serve_file()
        else:
            self.send_error(404)

    def _serve_catalog(self):
        epub_files = []
        if os.path.isdir(self.output_dir):
            epub_files = sorted(
                [f for f in os.listdir(self.output_dir) if f.lower().endswith(".epub")],
                reverse=True
            )

        entries = ""
        for fname in epub_files:
            fpath = os.path.join(self.output_dir, fname)
            size = os.path.getsize(fpath) if os.path.exists(fpath) else 0
            safe_name = fname.replace("&", "&amp;").replace("<", "&lt;")
            title = re.sub(r"_\d{4}-\d{2}-\d{2}\.epub$", "", fname.replace("_", " ")).strip()
            mtime = datetime.fromtimestamp(os.path.getmtime(fpath)).strftime("%Y-%m-%dT%H:%M:%SZ")
            entries += f"""
  <entry>
    <title>{safe_name}</title>
    <id>urn:x3sync:{fname}</id>
    <updated>{mtime}</updated>
    <summary>{title} ({size // 1024} KB)</summary>
    <link rel="http://opds-spec.org/acquisition" href="/opds/download/{fname}" type="application/epub+zip"/>
  </entry>"""

        xml = f"""<?xml version="1.0" encoding="utf-8"?>
<feed xmlns="http://www.w3.org/2005/Atom" xmlns:opds="http://opds-spec.org/2010/catalog">
  <title>X3 WebSync OPDS 카탈로그</title>
  <id>urn:x3sync:root</id>
  <updated>{datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')}</updated>
  <link rel="self" href="/opds" type="application/atom+xml;profile=opds-catalog"/>{entries}
</feed>"""
        body = xml.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/atom+xml;profile=opds-catalog; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _serve_file(self):
        fname = self.path[len("/opds/download/"):]
        fname = os.path.basename(fname)
        fpath = os.path.join(self.output_dir, fname)
        if not os.path.isfile(fpath):
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/epub+zip")
        self.send_header("Content-Disposition", f'attachment; filename="{fname}"')
        self.send_header("Content-Length", str(os.path.getsize(fpath)))
        self.end_headers()
        with open(fpath, "rb") as f:
            self.wfile.write(f.read())


class OPDSServer:
    """OPDS HTTP 서버를 백그라운드 스레드로 실행·관리하는 클래스"""

    def __init__(self, output_dir: str = "./output", port: int = 8765, bind_host: str = "127.0.0.1"):
        self.output_dir = output_dir
        self.port = port
        self.bind_host = bind_host
        self._server: Optional[HTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False

    def start(self) -> bool:
        if self._running:
            return True
        try:
            OPDSHandler.output_dir = self.output_dir
            self._server = HTTPServer((self.bind_host, self.port), OPDSHandler)
            self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
            self._thread.start()
            self._running = True
            return True
        except Exception as e:
            print(f"❌ OPDS 서버 시작 실패: {e}")
            return False

    def stop(self):
        if self._server:
            self._server.shutdown()
            self._server = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running

    def get_url(self) -> str:
        host = "localhost" if self.bind_host in ("127.0.0.1", "localhost") else self.bind_host
        return f"http://{host}:{self.port}/opds"
