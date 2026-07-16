"""config.json 설정 값 검증 유틸리티"""
import re
from websync.core.logger import get_logger

logger = get_logger()


def validate_config(config: dict) -> list[str]:
    """
    설정 값의 유효성을 검증합니다.
    Returns:
        오류 메시지 리스트. 비어있으면 유효.
    """
    errors: list[str] = []

    # 포트 범위 검증
    for section_key, port_key in [
        ("opds_server", "port"),
        ("web_dashboard", "port"),
    ]:
        section = config.get(section_key, {})
        port = section.get(port_key)
        if port is not None:
            try:
                port_int = int(port)
                if not (1024 <= port_int <= 65535):
                    errors.append(f"{section_key}.{port_key}: 포트 범위는 1024~65535여야 합니다 (현재: {port})")
            except (ValueError, TypeError):
                errors.append(f"{section_key}.{port_key}: 유효한 정수여야 합니다 (현재: {port})")

    # font_size 범위
    font_size = config.get("font_size")
    if font_size is not None:
        try:
            fs = int(font_size)
            if not (8 <= fs <= 48):
                errors.append(f"font_size: 8~48 범위여야 합니다 (현재: {font_size})")
        except (ValueError, TypeError):
            errors.append(f"font_size: 유효한 정수여야 합니다 (현재: {font_size})")

    # line_height 범위
    line_height = config.get("line_height")
    if line_height is not None:
        try:
            lh = float(line_height)
            if not (1.0 <= lh <= 3.0):
                errors.append(f"line_height: 1.0~3.0 범위여야 합니다 (현재: {line_height})")
        except (ValueError, TypeError):
            errors.append(f"line_height: 유효한 실수여야 합니다 (현재: {line_height})")

    # epub_merge_mode 검증
    merge_mode = config.get("epub_merge_mode", "per_site")
    if merge_mode not in ("per_site", "daily_digest"):
        errors.append(f"epub_merge_mode: 'per_site' 또는 'daily_digest'여야 합니다 (현재: {merge_mode})")

    # epub_theme 검증
    theme = config.get("epub_theme", "default")
    valid_themes = ("default", "serif_classic", "sans_modern", "dark_eink", "custom")
    if theme not in valid_themes:
        errors.append(f"epub_theme: {valid_themes} 중 하나여야 합니다 (현재: {theme})")

    # 사이트 검증
    for i, site in enumerate(config.get("sites", [])):
        site_errors = validate_site(site)
        for err in site_errors:
            errors.append(f"sites[{i}] ({site.get('name', '?')}): {err}")

    return errors


def validate_site(site: dict) -> list[str]:
    """개별 사이트 설정 검증"""
    errors: list[str] = []

    if not site.get("name", "").strip():
        errors.append("사이트 이름이 비어있습니다")

    url = site.get("url", "").strip()
    if not url:
        errors.append("URL이 비어있습니다")
    elif not (url.startswith("http://") or url.startswith("https://")):
        errors.append(f"URL은 http:// 또는 https://로 시작해야 합니다 (현재: {url[:50]})")

    site_type = site.get("type", "css")
    valid_types = ("css", "rss", "naver", "tistory", "brunch", "youtube", "substack", "naver_cafe", "naver_post", "soonsal", "moneyletter")
    if site_type not in valid_types:
        errors.append(f"타입이 유효하지 않습니다: {site_type}")

    limit = site.get("limit", 5)
    try:
        limit_int = int(limit)
        if not (1 <= limit_int <= 100):
            errors.append(f"limit: 1~100 범위여야 합니다 (현재: {limit})")
    except (ValueError, TypeError):
        errors.append(f"limit: 유효한 정수여야 합니다 (현재: {limit})")

    return errors


def log_validation_warnings(config: dict) -> None:
    """설정 검증 결과를 경고 로그로 출력합니다 (로드는 중단하지 않음)."""
    errors = validate_config(config)
    for err in errors:
        logger.warning(f"설정 검증 경고: {err}")
