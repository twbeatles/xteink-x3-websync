import os
import tempfile
import threading
import time
from websync.db.history import SyncHistoryDb


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
        db.mark_synced("https://example.com/1", "site", "title")
        assert db.is_synced("https://example.com/1")
    finally:
        _cleanup_db(db, path)


def test_concurrent_access():
    db, path = _make_db()
    try:
        def worker(i):
            url = f"https://example.com/{i}"
            db.mark_synced(url, "s", f"t{i}")
            db.is_synced(url)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        assert db.get_count() == 20
    finally:
        _cleanup_db(db, path)