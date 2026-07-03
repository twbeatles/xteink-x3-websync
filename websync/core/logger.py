import os
import logging
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime

from websync.core.paths import PROJECT_ROOT

_logger_initialized = False
_app_logger = None


def get_logger() -> logging.Logger:
    global _logger_initialized, _app_logger
    if _logger_initialized:
        return _app_logger

    log_dir = os.path.join(PROJECT_ROOT, "logs")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"sync_{datetime.now().strftime('%Y-%m-%d')}.log")

    logger = logging.getLogger("x3_websync")
    logger.setLevel(logging.DEBUG)

    fh = RotatingFileHandler(log_file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s", datefmt="%Y-%m-%d %H:%M:%S"))

    if sys.stdout and hasattr(sys.stdout, "write"):
        ch = logging.StreamHandler(sys.stdout)
        ch.setLevel(logging.INFO)
        ch.setFormatter(logging.Formatter("%(message)s"))
        logger.addHandler(ch)

    logger.addHandler(fh)
    _app_logger = logger
    _logger_initialized = True
    return logger


def get_log_dir() -> str:
    return os.path.join(PROJECT_ROOT, "logs")
