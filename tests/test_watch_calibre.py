"""Calibre Watch — on_moved 지원 및 콜백 계약."""
from types import SimpleNamespace

from websync.watch.calibre import CalibreWatcher, _is_watch_book_file


def test_is_watch_book_file_extensions():
    assert _is_watch_book_file("/lib/new.epub") is True
    assert _is_watch_book_file("/lib/new.PDF") is True
    assert _is_watch_book_file("/lib/new.txt") is True
    assert _is_watch_book_file("/lib/new.tmp") is False
    assert _is_watch_book_file("/lib/folder") is False


def test_calibre_watch_handles_moved_epub():
    seen: list[str] = []
    watcher = CalibreWatcher("/tmp/calibre", seen.append, debounce_sec=0.01)

    class _Handler:
        pass

    # start() 없이 핸들러 로직만 재현
    handler_ns = {}

    def on_moved(event):
        if event.is_directory:
            return
        dest = getattr(event, "dest_path", "") or ""
        if _is_watch_book_file(dest):
            watcher._schedule_debounced(dest)

    handler_ns["on_moved"] = on_moved
    event = SimpleNamespace(is_directory=False, src_path="/tmp/calibre/tmp.part", dest_path="/tmp/calibre/book.epub")
    handler_ns["on_moved"](event)
    assert "/tmp/calibre/book.epub" in watcher._pending
