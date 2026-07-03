import sys
import argparse
from datetime import datetime

# 분할 모듈 임포트
from config_manager import ConfigManager
from service import SyncService
from gui import SyncAppGui

# 윈도우 콘솔 UnicodeEncodeError 방지를 위한 UTF-8 설정
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

def main():
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

if __name__ == "__main__":
    main()
