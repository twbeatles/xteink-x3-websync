"""Calibre 서재 폴더 변경 감시 모듈 (watchdog 사용)"""
import os
import threading
from typing import Callable, Optional


class CalibreWatcher:
    """Calibre 라이브러리 폴더에 새 파일이 추가되면 콜백을 호출하는 감시자"""

    def __init__(self, watch_dir: str, on_new_file: Callable[[str], None]):
        self.watch_dir = watch_dir
        self.on_new_file = on_new_file
        self._observer: Optional[object] = None
        self._running = False

    def start(self) -> bool:
        if self._running:
            return True
        if not os.path.isdir(self.watch_dir):
            print(f"⚠️ 감시 폴더가 없습니다: {self.watch_dir}")
            return False
        try:
            from watchdog.observers import Observer
            from watchdog.events import FileSystemEventHandler

            watcher_self = self

            class _Handler(FileSystemEventHandler):
                def on_created(self, event):
                    if event.is_directory:
                        return
                    fpath = event.src_path
                    ext = os.path.splitext(fpath)[1].lower()
                    if ext in (".epub", ".pdf", ".mobi", ".txt", ".azw3"):
                        watcher_self.on_new_file(fpath)

            self._observer = Observer()
            self._observer.schedule(_Handler(), self.watch_dir, recursive=True)
            self._observer.start()
            self._running = True
            return True
        except ImportError:
            print("❌ watchdog 패키지가 없습니다. pip install watchdog 를 실행하세요.")
            return False
        except Exception as e:
            print(f"❌ 파일 감시 시작 실패: {e}")
            return False

    def stop(self):
        if self._observer:
            self._observer.stop()
            self._observer.join(timeout=3)
            self._observer = None
        self._running = False

    @property
    def is_running(self) -> bool:
        return self._running
