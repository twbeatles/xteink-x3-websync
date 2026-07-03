import os
import tempfile
from websync.upload.uploader import X3Uploader


def test_sanitize_filename_korean():
    u = X3Uploader("127.0.0.1")
    name = u._sanitize_filename("/tmp/한글 제목 테스트.epub")
    assert " " not in name
    assert name.endswith(".epub")


def test_build_target_list_dedup():
    u = X3Uploader("192.168.1.10", devices=[{"name": "추가", "ip": "192.168.1.20"}, {"name": "dup", "ip": "192.168.1.10"}])
    targets = u._build_target_list()
    ips = [t["ip"] for t in targets]
    assert ips.count("192.168.1.10") == 1
    assert "192.168.1.20" in ips


def test_calc_timeout_scales_with_size():
    u = X3Uploader("127.0.0.1")
    with tempfile.NamedTemporaryFile(delete=False) as f:
        f.write(b"x" * (2 * 1024 * 1024))
        path = f.name
    try:
        assert u._calc_timeout(path) >= 30
    finally:
        os.remove(path)