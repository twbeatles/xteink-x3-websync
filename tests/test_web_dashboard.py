import json
import tempfile
import urllib.error
import urllib.request

import pytest

from websync.servers.web_dashboard import WebDashboard


def _free_port() -> int:
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _start_dashboard(**kwargs) -> WebDashboard:
    port = kwargs.pop("port", _free_port())
    srv = WebDashboard(port=port, bind_host="127.0.0.1", **kwargs)
    assert srv.start() is True
    return srv


def test_web_dashboard_refuses_empty_token():
    srv = WebDashboard(port=_free_port(), bind_host="127.0.0.1", api_token="")
    assert srv.start() is False


def test_dashboard_html_requires_auth():
    srv = _start_dashboard(api_token="tok123")
    try:
        url = f"http://127.0.0.1:{srv.port}/dashboard"
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(url, timeout=3)
        assert exc.value.code == 401
    finally:
        srv.stop()


def test_api_sync_requires_bearer():
    busy = {"running": False}

    def busy_cb():
        return busy["running"]

    def sync_cb():
        return True

    srv = _start_dashboard(
        api_token="tok123",
        pipeline_busy_callback=busy_cb,
        sync_callback=sync_cb,
    )
    try:
        url = f"http://127.0.0.1:{srv.port}/api/sync"
        req = urllib.request.Request(url, method="POST")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=3)
        assert exc.value.code == 401

        req = urllib.request.Request(url, method="POST", headers={"Authorization": "Bearer tok123"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status in (200, 202)
            data = json.loads(resp.read())
        assert "message" in data
    finally:
        srv.stop()


def test_api_sync_busy_response():
    srv = _start_dashboard(
        api_token="tok123",
        pipeline_busy_callback=lambda: True,
    )
    try:
        url = f"http://127.0.0.1:{srv.port}/api/sync"
        req = urllib.request.Request(url, method="POST", headers={"Authorization": "Bearer tok123"})
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=3)
        assert exc.value.code == 409
        body = json.loads(exc.value.read().decode())
        assert "이미 실행" in body.get("message", "")
    finally:
        srv.stop()


def test_api_sync_callback_false_returns_409():
    """sync_callback 이 False(락 거부 등)를 반환하면 202 성공이 아니라 409."""
    srv = _start_dashboard(
        api_token="tok123",
        pipeline_busy_callback=lambda: False,
        sync_callback=lambda: False,
    )
    try:
        url = f"http://127.0.0.1:{srv.port}/api/sync"
        req = urllib.request.Request(
            url, method="POST", headers={"Authorization": "Bearer tok123"}
        )
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=3)
        assert exc.value.code == 409
        body = json.loads(exc.value.read().decode())
        assert body.get("ok") is False
        assert body.get("started") is False
    finally:
        srv.stop()


def test_api_sync_accepted_includes_started_flag():
    srv = _start_dashboard(
        api_token="tok123",
        pipeline_busy_callback=lambda: False,
        sync_callback=lambda: True,
    )
    try:
        url = f"http://127.0.0.1:{srv.port}/api/sync"
        req = urllib.request.Request(
            url, method="POST", headers={"Authorization": "Bearer tok123"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            assert resp.status == 202
            data = json.loads(resp.read())
        assert data.get("ok") is True
        assert data.get("started") is True
    finally:
        srv.stop()


def test_api_status_returns_last_result():
    srv = _start_dashboard(
        api_token="tok123",
        get_status_callback=lambda: {"status": "no_new", "success": True},
    )
    try:
        url = f"http://127.0.0.1:{srv.port}/api/status"
        req = urllib.request.Request(url, headers={"Authorization": "Bearer tok123"})
        with urllib.request.urlopen(req, timeout=3) as resp:
            data = json.loads(resp.read())
        assert data["last_result"]["status"] == "no_new"
    finally:
        srv.stop()


def test_login_sets_session_cookie():
    srv = _start_dashboard(api_token="tok123")
    try:
        url = f"http://127.0.0.1:{srv.port}/api/login"
        body = json.dumps({"token": "tok123"}).encode()
        req = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": "Bearer tok123"},
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            cookies = resp.headers.get("Set-Cookie", "")
            assert "x3sync_session=" in cookies
    finally:
        srv.stop()


# --- N6: ThreadingHTTPServer 동시 요청 처리 ---

def test_dashboard_serves_concurrent_status_requests():
    """느린 sync_callback 실행 중에도 /api/status 요청이 블로킹되지 않는지."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    started = threading.Event()
    release = threading.Event()

    def slow_sync_cb():
        started.set()
        release.wait(timeout=5)
        return True

    srv = _start_dashboard(
        api_token="tok123",
        pipeline_busy_callback=lambda: False,
        sync_callback=slow_sync_cb,
        get_status_callback=lambda: {"status": "no_new", "success": True},
    )
    try:
        sync_url = f"http://127.0.0.1:{srv.port}/api/sync"
        status_url = f"http://127.0.0.1:{srv.port}/api/status"
        results = {}

        def trigger_sync():
            req = urllib.request.Request(
                sync_url, method="POST", headers={"Authorization": "Bearer tok123"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                results["sync_status"] = resp.status

        def fetch_status():
            # sync_cb 가 블로킹 중일 때 status 가 바로 응답하는지
            with urllib.request.urlopen(
                urllib.request.Request(status_url, headers={"Authorization": "Bearer tok123"}),
                timeout=5,
            ) as resp:
                results["status"] = json.loads(resp.read())["last_result"]["status"]

        with ThreadPoolExecutor(max_workers=2) as ex:
            sync_fut = ex.submit(trigger_sync)
            assert started.wait(timeout=3)  # sync_cb 진입 확인
            # sync 가 release 대기 중일 때 status 요청 — 즉시 응답해야
            status_fut = ex.submit(fetch_status)
            status_fut.result(timeout=5)
            release.set()
            sync_fut.result(timeout=10)

        assert results["status"] == "no_new"
        assert results["sync_status"] == 202
    finally:
        srv.stop()
