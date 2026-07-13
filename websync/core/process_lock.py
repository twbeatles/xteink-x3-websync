"""크로스 프로세스 파일 락 (동기화 파이프라인 직렬화용)"""
from __future__ import annotations

import os
import sys
import tempfile
import time
from typing import Optional


DEFAULT_PIPELINE_LOCK_NAME = "x3_websync_pipeline.lock"


class ProcessFileLock:
    """
    프로세스 간 배타 락.
    - Unix: fcntl.flock
    - Windows: msvcrt.locking
    락을 잡은 동안 파일 핸들을 유지합니다.
    """

    def __init__(self, lock_path: str | None = None):
        if lock_path is None:
            lock_path = os.path.join(tempfile.gettempdir(), DEFAULT_PIPELINE_LOCK_NAME)
        self.lock_path = lock_path
        self._fh: Optional[object] = None
        self._held = False

    @property
    def held(self) -> bool:
        return self._held

    def acquire(self, blocking: bool = False, timeout: float = 0.0) -> bool:
        """락 획득. 성공 시 True."""
        if self._held:
            return True

        deadline = None if not blocking else (time.monotonic() + max(timeout, 0.0))
        while True:
            if self._try_acquire_once():
                return True
            if not blocking:
                return False
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.05)

    def _try_acquire_once(self) -> bool:
        try:
            os.makedirs(os.path.dirname(self.lock_path) or ".", exist_ok=True)
            # a+ 로 열고 배타 바이트 락
            fh = open(self.lock_path, "a+", encoding="utf-8")
            try:
                if sys.platform == "win32":
                    import msvcrt

                    fh.seek(0)
                    if fh.read(1) == "":
                        fh.write("0")
                        fh.flush()
                    fh.seek(0)
                    msvcrt.locking(fh.fileno(), msvcrt.LK_NBLCK, 1)
                else:
                    import fcntl

                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                fh.seek(0)
                fh.truncate()
                fh.write(f"{os.getpid()}\n")
                fh.flush()
            except OSError:
                fh.close()
                return False
            self._fh = fh
            self._held = True
            return True
        except OSError:
            return False

    def release(self) -> None:
        if not self._held or self._fh is None:
            self._held = False
            self._fh = None
            return
        try:
            if sys.platform == "win32":
                import msvcrt

                try:
                    self._fh.seek(0)
                    msvcrt.locking(self._fh.fileno(), msvcrt.LK_UNLCK, 1)
                except OSError:
                    pass
            else:
                import fcntl

                try:
                    fcntl.flock(self._fh.fileno(), fcntl.LOCK_UN)
                except OSError:
                    pass
        finally:
            try:
                self._fh.close()
            except OSError:
                pass
            self._fh = None
            self._held = False

    def is_held_by_other(self) -> bool:
        """다른 프로세스가 락을 잡고 있는지 비파괴 검사 (try-lock)."""
        if self._held:
            return False
        probe = ProcessFileLock(self.lock_path)
        if probe.acquire(blocking=False):
            probe.release()
            return False
        return True

    def __enter__(self):
        if not self.acquire(blocking=True, timeout=30.0):
            raise TimeoutError(f"프로세스 락 획득 실패: {self.lock_path}")
        return self

    def __exit__(self, exc_type, exc, tb):
        self.release()
        return False
