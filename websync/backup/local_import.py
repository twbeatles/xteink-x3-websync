"""실행 폴더의 레거시/사이드카 JSON 을 로컬 캐시에 합집합 반영.

dist 배포물에서 흔히 같이 두는 파일:
- synced_posts.json  (kind=synced_posts, posts[])
- *설정백업*.json / sites.json  (export_version + sites[])
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

from websync.backup.atomic_io import read_json_safe
from websync.backup.format import (
    HISTORY_FILENAME,
    SITES_FILENAME,
    extract_posts,
    extract_sites,
    merge_sites,
)
from websync.backup.portable_cfg import apply_portable_cfg, get_portable_cfg
from websync.config.manager import ConfigManager
from websync.core.paths import PROJECT_ROOT
from websync.db.history import SyncHistoryDb, SyncHistoryDbError


def _list_sidecar_site_files(root: str) -> list[str]:
    """사이트 백업 후보 경로 (존재하는 것만)."""
    candidates: list[str] = []
    # 표준 이름
    for name in (SITES_FILENAME,):
        path = os.path.join(root, name)
        if os.path.isfile(path):
            candidates.append(path)
    # 사용자가 둔 "*설정백업*.json" 등 (sites 키 있는 파일)
    try:
        for entry in os.listdir(root):
            lower = entry.lower()
            if not lower.endswith(".json"):
                continue
            if entry in (HISTORY_FILENAME, "config.json", "config.json.bak", "manifest.json"):
                continue
            if "설정백업" in entry or "sites" in lower or "backup" in lower:
                path = os.path.join(root, entry)
                if os.path.isfile(path) and path not in candidates:
                    candidates.append(path)
    except OSError:
        pass
    return candidates


def import_local_sidecars(
    config_manager: ConfigManager,
    db: SyncHistoryDb,
    *,
    root: str | None = None,
    logger: Optional[logging.Logger] = None,
) -> dict[str, Any]:
    """PROJECT_ROOT(또는 root)의 이력·사이트 JSON 을 로컬에 병합.

    Returns:
        {ok, history_changed, sites_changed, sites_added, messages, files}
    """
    log = logger or logging.getLogger("websync.backup")
    base = root if root is not None else PROJECT_ROOT
    result: dict[str, Any] = {
        "ok": True,
        "history_changed": 0,
        "sites_changed": False,
        "sites_added": 0,
        "messages": [],
        "files": [],
    }

    # --- history: synced_posts.json ---
    hist_path = os.path.join(base, HISTORY_FILENAME)
    if os.path.isfile(hist_path):
        payload = read_json_safe(hist_path)
        posts, _ = extract_posts(payload)
        if posts:
            try:
                n = db.import_posts_union(posts)
                result["history_changed"] = n
                result["files"].append(hist_path)
                msg = f"로컬 {HISTORY_FILENAME}: 이력 {len(posts)}건 중 {n}건 반영"
                result["messages"].append(msg)
                log.info(msg)
            except SyncHistoryDbError as e:
                result["ok"] = False
                msg = f"로컬 {HISTORY_FILENAME} 가져오기 실패: {e}"
                result["messages"].append(msg)
                log.error(msg)

    # --- sites: sites.json / *설정백업*.json ---
    config = config_manager.load_config()
    local_sites = config.get("sites") if isinstance(config.get("sites"), list) else []
    before_urls = {
        (s.get("url") or "").strip().lower()
        for s in local_sites
        if isinstance(s, dict) and s.get("url")
    }
    merged = list(local_sites)
    sites_from_files = 0

    for path in _list_sidecar_site_files(base):
        payload = read_json_safe(path)
        remote_sites, _ = extract_sites(payload)
        if not remote_sites:
            continue
        # 설정 백업은 보통 최신 정본에 가깝 → 동일 URL 은 remote 우선
        merged = merge_sites(merged, remote_sites, remote_wins_same_url=True)
        sites_from_files += len(remote_sites)
        result["files"].append(path)
        result["messages"].append(f"로컬 사이트 파일 병합: {os.path.basename(path)} ({len(remote_sites)}개)")

    if sites_from_files and merged != local_sites:
        after_urls = {
            (s.get("url") or "").strip().lower()
            for s in merged
            if isinstance(s, dict) and s.get("url")
        }

        def _apply(cfg: dict) -> None:
            cur = cfg.get("sites") if isinstance(cfg.get("sites"), list) else []
            # 디스크 최신과 다시 병합
            remote_all: list[dict] = []
            for path in _list_sidecar_site_files(base):
                payload = read_json_safe(path)
                rs, _ = extract_sites(payload)
                remote_all.extend(rs)
            cfg["sites"] = merge_sites(cur, remote_all, remote_wins_same_url=True)

        try:
            config_manager.update_config(_apply)
        except Exception:
            config["sites"] = merged
            config_manager.save_config(config)
        result["sites_changed"] = True
        result["sites_added"] = len(after_urls - before_urls)
        log.info(
            "로컬 사이트 사이드카 병합: +%s URL (파일 %s개)",
            result["sites_added"],
            sites_from_files,
        )

    return result


def ensure_wizard_skips_if_sidecars_present(config: dict, root: str | None = None) -> bool:
    """사이드카 JSON 이 있으면 첫 실행 마법사 부담을 줄이도록 힌트.

    wizard_completed 를 강제하지는 않고, 호출측에서 참고할 수 있게 여부만 반환.
    """
    base = root if root is not None else PROJECT_ROOT
    if os.path.isfile(os.path.join(base, HISTORY_FILENAME)):
        return True
    return bool(_list_sidecar_site_files(base))
