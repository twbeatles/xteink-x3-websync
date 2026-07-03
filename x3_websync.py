import sys
import os
import argparse
import tempfile
from datetime import datetime

# 윈도우 pythonw.exe 구동 시 sys.stdout / sys.stderr 가 None 이 되는 현상 대처
class NullWriter:
    def write(self, s):
        pass
    def flush(self):
        pass

if sys.stdout is None:
    sys.stdout = NullWriter()
if sys.stderr is None:
    sys.stderr = NullWriter()

# 윈도우 콘솔 UnicodeEncodeError 방지를 위한 UTF-8 설정
if sys.platform == 'win32':
    try:
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

from websync.config.manager import ConfigManager
from websync.pipeline.service import SyncService
from websync.gui.app import SyncAppGui
from websync.core.logger import get_logger


lock_file = None
LOCK_FILENAME = "x3_websync_instance.lock"


def _lock_path() -> str:
    return os.path.join(tempfile.gettempdir(), LOCK_FILENAME)


def _is_process_running(pid: int) -> bool:
    if pid <= 0:
        return False
    if sys.platform == "win32":
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _read_lock_pid(lock_path: str) -> int | None:
    try:
        with open(lock_path, "r", encoding="utf-8") as f:
            line = f.read().strip()
        if not line:
            return None
        return int(line.split(",")[0])
    except (OSError, ValueError):
        return None


def _remove_stale_lock(lock_path: str) -> bool:
    """락 파일이 남았지만 프로세스가 없으면 제거합니다."""
    if not os.path.exists(lock_path):
        return False
    pid = _read_lock_pid(lock_path)
    if pid is None or not _is_process_running(pid):
        try:
            os.remove(lock_path)
            return True
        except OSError:
            pass
    return False


def acquire_instance_lock() -> bool:
    """단일 인스턴스 기동 검사 (stale 락 파일 복구 포함)"""
    global lock_file
    lock_path = _lock_path()
    _remove_stale_lock(lock_path)

    payload = f"{os.getpid()},{datetime.now().isoformat()}"

    try:
        if sys.platform == "win32":
            lock_file = os.open(lock_path, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
            os.write(lock_file, payload.encode("utf-8"))
        else:
            lock_file = open(lock_path, "x", encoding="utf-8")
            lock_file.write(payload)
            lock_file.flush()
            import fcntl
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, FileExistsError):
        if _remove_stale_lock(lock_path):
            return acquire_instance_lock()
        return False


def release_instance_lock():
    """인스턴스 락 해제"""
    global lock_file
    lock_path = _lock_path()
    if lock_file is not None:
        try:
            if sys.platform == "win32":
                os.close(lock_file)
            else:
                lock_file.close()
        except Exception:
            pass
        lock_file = None
    try:
        if os.path.exists(lock_path):
            os.remove(lock_path)
    except Exception:
        pass


def main():
    parser = argparse.ArgumentParser(description="Xteink X3 WebSync CLI / GUI Manager")
    parser.add_argument(
        "--sync",
        action="store_true",
        help="GUI 없이 config.json 기준 즉시 동기화 (스케줄러 연동용)"
    )
    args = parser.parse_args()

    # GUI만 단일 인스턴스 락 — --sync는 파이프라인 락(SyncService)만 사용해 GUI 실행 중에도 동작
    gui_lock_acquired = False
    if not args.sync:
        if not acquire_instance_lock():
            print(f"[{datetime.now()}] ⚠️ 경고: 이미 다른 X3 WebSync GUI가 실행 중입니다. 실행을 중단합니다.")
            sys.exit(1)
        gui_lock_acquired = True

    try:
        logger = get_logger()
        logger.info("=" * 60)
        logger.info(f"X3 WebSync 시작 (PID: {os.getpid()}, mode={'sync' if args.sync else 'gui'})")

        try:
            config_manager = ConfigManager()
            service = SyncService(config_manager)
        except Exception as e:
            print(f"[{datetime.now()}] ❌ 설정 로드 실패: {e}")
            sys.exit(1)

        if args.sync:
            print(f"[{datetime.now()}] 백그라운드 동기화 모드 구동 시작")
            success = service.run_sync_pipeline()
            print(f"[{datetime.now()}] 백그라운드 동기화 모드 종료 (결과: {success})")
            sys.exit(0 if success else 1)
        else:
            app = SyncAppGui(service)
            app.run()
    finally:
        if gui_lock_acquired:
            release_instance_lock()


if __name__ == "__main__":
    main()
