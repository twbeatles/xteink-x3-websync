import os
import tempfile
import urllib.error
import urllib.request

import pytest

from websync.servers.opds import OPDSServer


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_server(tmp_output: str, *, require_auth: bool = False, api_key: str = "secret-key") -> OPDSServer:
    port = _free_port()
    srv = OPDSServer(
        output_dir=tmp_output,
        port=port,
        bind_host="127.0.0.1",
        api_key=api_key,
        require_auth=require_auth,
    )
    assert srv.start() is True
    return srv


def test_opds_catalog_localhost_no_auth():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "book_2026-01-01.epub"), "wb") as f:
            f.write(b"epub")
        srv = _start_server(tmp, require_auth=False)
        try:
            url = f"http://127.0.0.1:{srv.port}/opds"
            with urllib.request.urlopen(url, timeout=3) as resp:
                body = resp.read().decode("utf-8")
            assert "book_2026-01-01.epub" in body
        finally:
            srv.stop()


def test_opds_lan_requires_api_key():
    with tempfile.TemporaryDirectory() as tmp:
        srv = _start_server(tmp, require_auth=True, api_key="mykey")
        try:
            url = f"http://127.0.0.1:{srv.port}/opds"
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(url, timeout=3)
            assert exc.value.code == 401

            req = urllib.request.Request(url, headers={"X-Api-Key": "mykey"})
            with urllib.request.urlopen(req, timeout=3) as resp:
                assert resp.status == 200
        finally:
            srv.stop()


def test_opds_download_rejects_non_epub():
    with tempfile.TemporaryDirectory() as tmp:
        with open(os.path.join(tmp, "evil.exe"), "wb") as f:
            f.write(b"x")
        srv = _start_server(tmp)
        try:
            url = f"http://127.0.0.1:{srv.port}/opds/download/evil.exe"
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(url, timeout=3)
            assert exc.value.code == 403
        finally:
            srv.stop()


def test_opds_path_traversal_blocked():
    with tempfile.TemporaryDirectory() as tmp:
        srv = _start_server(tmp)
        try:
            url = f"http://127.0.0.1:{srv.port}/opds/download/..%2F..%2Fetc%2Fpasswd"
            with pytest.raises(urllib.error.HTTPError) as exc:
                urllib.request.urlopen(url, timeout=3)
            assert exc.value.code in (403, 404)
        finally:
            srv.stop()