"""프로젝트 루트 기준 경로 해석 유틸리티"""
import os
import sys


def _detect_project_root() -> str:
    """
    개발 모드: websync 패키지 상위 디렉터리.
    PyInstaller frozen: 실행 파일(exe)이 있는 디렉터리.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    pkg_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.dirname(pkg_dir)


PROJECT_ROOT = _detect_project_root()


def resolve_path(path: str) -> str:
    """상대 경로를 프로젝트 루트 기준 절대 경로로 변환합니다."""
    if not path:
        return PROJECT_ROOT
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(PROJECT_ROOT, path))
