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
        # sys.stdout이 NullWriter가 아닐 경우에만 reconfigure 시도
        if hasattr(sys.stdout, 'reconfigure'):
            sys.stdout.reconfigure(encoding='utf-8')
        if hasattr(sys.stderr, 'reconfigure'):
            sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# 분할 모듈 임포트
from config_manager import ConfigManager
from service import SyncService
from gui import SyncAppGui

# 프로그램 다중 실행 방지용 파일 락 변수 보존
lock_file = None

def acquire_instance_lock():
    """단일 인스턴스 기동 검사 (Race Condition 중복 실행 방지)"""
    global lock_file
    lock_path = os.path.join(tempfile.gettempdir(), "x3_websync_instance.lock")
    try:
        # 파일 오픈 및 락 홀드 시도 (윈도우 전용 파일 잠금 획득 우회용 os.open Flags 사용)
        if sys.platform == "win32":
            # 윈도우에서는 타 프로세스 공유 쓰기/읽기를 방지하여 독점 락 생성
            lock_file = os.open(lock_path, os.O_CREAT | os.O_WRONLY | os.O_EXCL)
        else:
            lock_file = open(lock_path, "w")
            import fcntl
            fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except (OSError, FileExistsError):
        return False

def release_instance_lock():
    """인스턴스 락 해제"""
    global lock_file
    if lock_file is not None:
        try:
            if sys.platform == "win32":
                os.close(lock_file)
            else:
                lock_file.close()
            lock_path = os.path.join(tempfile.gettempdir(), "x3_websync_instance.lock")
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except Exception:
            pass

def main():
    if not acquire_instance_lock():
        print(f"[{datetime.now()}] ⚠️ 경고: 이미 다른 X3 WebSync 프로그램 인스턴스가 실행 중입니다. 실행을 중단합니다.")
        sys.exit(1)

    try:
        parser = argparse.ArgumentParser(description="Xteink X3 WebSync CLI / GUI Manager")
        parser.add_argument(
            "--sync", 
            action="store_true", 
            help="GUI 창을 띄우지 않고, 현재 설정파일(config.json)을 바탕으로 즉시 스크래핑 및 동기화 작업만 실행합니다. (스케줄러 연동용)"
        )
        args = parser.parse_args()

        config_manager = ConfigManager()
        service = SyncService(config_manager)

        if args.sync:
            print(f"[{datetime.now()}] 백그라운드 동기화 모드 구동 시작")
            success = service.run_sync_pipeline()
            print(f"[{datetime.now()}] 백그라운드 동기화 모드 종료 (결과: {success})")
            sys.exit(0 if success else 1)
        else:
            app = SyncAppGui(service)
            app.run()
    finally:
        release_instance_lock()

if __name__ == "__main__":
    main()

