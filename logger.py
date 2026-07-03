import os
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime

_logger_initialized = False
_app_logger = None

def get_logger() -> logging.Logger:
    """앱 전역 로거 인스턴스를 반환. 한 번만 초기화됨."""
    global _logger_initialized, _app_logger
    if _logger_initialized:
        return _app_logger

    log_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, f"sync_{datetime.now().strftime('%Y-%m-%d')}.log")

    logger = logging.getLogger("x3_websync")
    logger.setLevel(logging.DEBUG)

    # 파일 핸들러: 최대 5MB, 백업 3개
    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

    # 콘솔 핸들러 (pythonw에서도 안전하게)
    import sys
    if sys.stdout and hasattr(sys.stdout, 'write'):
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    logger.addHandler(fh)
    _app_logger = logger
    _logger_initialized = True
    return logger


def get_log_dir() -> str:
    """현재 로그 파일이 저장되는 폴더 경로 반환"""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs")
