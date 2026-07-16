"""HTML 템플릿 로더 (개발 / PyInstaller frozen)."""
from __future__ import annotations

import os
import sys

from websync.core.logger import get_logger

logger = get_logger()


def load_template(name: str) -> str:
    """HTML 템플릿 파일을 읽어옵니다. sys.frozen 및 PyInstaller 대응."""
    if getattr(sys, "frozen", False):
        if hasattr(sys, "_MEIPASS"):
            base_dir = os.path.join(sys._MEIPASS, "websync", "servers", "templates")
        else:
            base_dir = os.path.join(os.path.dirname(sys.executable), "servers", "templates")
    else:
        base_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
        )

    path = os.path.join(base_dir, name)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        logger.error(f"템플릿 로드 실패 ({name}): {e}")
        return f"Template {name} not found."


def login_html() -> str:
    return load_template("login.html")


def dashboard_html() -> str:
    return load_template("dashboard.html")
