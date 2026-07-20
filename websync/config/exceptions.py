"""설정 관리 예외"""


class ConfigLoadError(Exception):
    """config.json 로드·파싱 실패"""

    def __init__(self, message: str, corrupt_path: str | None = None):
        super().__init__(message)
        self.corrupt_path = corrupt_path


class ConfigSaveError(Exception):
    """config.json 저장 실패"""


class ConfigConflictError(ConfigSaveError):
    """다른 경로가 config.json을 먼저 갱신해 저장이 거부됨 (revision CAS)."""

    def __init__(self, message: str, disk_config: dict | None = None):
        super().__init__(message)
        self.disk_config = disk_config
