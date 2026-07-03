"""프로젝트 루트 기준 경로 해석 유틸리티"""
import os

_PKG_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(_PKG_DIR)


def resolve_path(path: str) -> str:
    """상대 경로를 프로젝트 루트 기준 절대 경로로 변환합니다."""
    if not path:
        return PROJECT_ROOT
    if os.path.isabs(path):
        return os.path.normpath(path)
    return os.path.normpath(os.path.join(PROJECT_ROOT, path))
