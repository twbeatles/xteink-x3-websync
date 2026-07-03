"""설정 관리 예외"""


class ConfigLoadError(Exception):
    """config.json 로드·파싱 실패"""

    def __init__(self, message: str, corrupt_path: str | None = None):
        super().__init__(message)
        self.corrupt_path = corrupt_path