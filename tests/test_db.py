import os
import sqlite3
import tempfile
import threading
import time

import pytest

from websync.db.history import SyncHistoryDb, SyncHistoryDbError, LEGACY_DEVICE_IP


def _make_db() -> tuple[SyncHistoryDb, str]:
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    return SyncHistoryDb(path), path


def _cleanup_db(db: SyncHistoryDb, path: str):
    del db
    time.sleep(0.05)
    try:
        os.remove(path)
    except OSError:
        pass


def test_mark_and_is_synced():
    db, path = _make_db()
    try:
        assert not db.is_synced("https://example.com/1")
        db.mark_synced("https://example.com/1", "site", "title", device_ip="192.168.1.1")
        assert db.is_synced("https://example.com/1")
        assert db.is_synced_for_device("https://example.com/1", "192.168.1.1")
    finally:
        _cleanup_db(db, path)


def test_needs_sync_per_device():
    db, path = _make_db()
    try:
        url = "https://example.com/1"
        db.mark_synced(url, "site", "title", device_ip="10.0.0.1")
        assert db.needs_sync(url, ["10.0.0.1", "10.0.0.2"])
        assert not db.needs_sync(url, ["10.0.0.1"])
        db.mark_synced(url, "site", "title", device_ip="10.0.0.2")
        assert not db.needs_sync(url, ["10.0.0.1", "10.0.0.2"])
    finally:
        _cleanup_db(db, path)


def test_legacy_migration():
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with sqlite3.connect(path) as conn:
            conn.execute("""
                CREATE TABLE synced_posts (
                    url TEXT PRIMARY KEY,
                    site_name TEXT,
                    title TEXT,
                    synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute(
                "INSERT INTO synced_posts (url, site_name, title) VALUES (?, ?, ?)",
                ("https://legacy.com/1", "s", "t"),
            )
            conn.commit()
        db = SyncHistoryDb(path)
        assert db.is_synced_for_device("https://legacy.com/1", "192.168.0.5")
    finally:
        try:
            os.remove(path)
        except OSError:
            pass


def test_delete_entry_raises_on_error():
    db, path = _make_db()
    try:
        db.mark_synced("https://x.com/1", "s", "t", device_ip="1.1.1.1")
        # 잘못된 경로로 연결 유도: db_path 변경 후 delete
        db.db_path = os.path.join(tempfile.gettempdir(), "nonexistent_dir_xyz", "no.db")
        with pytest.raises(SyncHistoryDbError):
            db.delete_entry("https://x.com/1")
    finally:
        # path 원본 정리는 실패할 수 있음
        try:
            _cleanup_db(db, path)
        except Exception:
            pass


def test_concurrent_access():
    db, path = _make_db()
    try:
        def worker(i):
            url = f"https://example.com/{i}"
            db.mark_synced(url, "s", f"t{i}", device_ip=f"10.0.0.{i % 5}")
            db.is_synced(url)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert db.get_count() == 20
    finally:
        _cleanup_db(db, path)


def test_is_synced_raises_on_db_error():
    from unittest.mock import patch

    db, path = _make_db()
    try:
        db.mark_synced("https://example.com/x", "s", "t", device_ip="1.1.1.1")

        def bad_connect(*args, **kwargs):
            raise sqlite3.OperationalError("database is locked")

        with patch("websync.db.history.sqlite3.connect", side_effect=bad_connect):
            with pytest.raises(SyncHistoryDbError):
                db.is_synced("https://example.com/x")
    finally:
        _cleanup_db(db, path)


def test_mark_synced_raises_on_db_error():
    from unittest.mock import patch

    db, path = _make_db()
    try:
        def bad_connect(*args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")

        with patch("websync.db.history.sqlite3.connect", side_effect=bad_connect):
            with pytest.raises(SyncHistoryDbError):
                db.mark_synced("https://example.com/x", "s", "t", device_ip="1.1.1.1")
    finally:
        _cleanup_db(db, path)


def test_init_db_failure_raises():
    from unittest.mock import patch

    with patch("websync.db.history.sqlite3.connect", side_effect=OSError("permission denied")):
        with pytest.raises(SyncHistoryDbError, match="DB 초기화 실패"):
            SyncHistoryDb(os.path.join(tempfile.gettempdir(), "nonexistent_sub/db.db"))