"""OneDrive 등 클라우드 폴더 백업 동기화 서비스."""
from __future__ import annotations

import logging
import os
import threading
from typing import Any, Optional

from websync.backup.atomic_io import ensure_dir, read_json_safe, write_json_atomic
from websync.backup.format import (
    HISTORY_FILENAME,
    LOCK_FILENAME,
    MANIFEST_FILENAME,
    SITES_FILENAME,
    build_history_payload,
    build_manifest,
    build_sites_payload,
    extract_posts,
    extract_sites,
    is_remote_newer,
    merge_sites,
    now_iso,
)
from websync.config.manager import ConfigManager
from websync.core.paths import resolve_path
from websync.core.process_lock import ProcessFileLock
from websync.db.history import SyncHistoryDb, SyncHistoryDbError


class BackupSyncError(Exception):
    """백업 동기화 실패"""


class BackupSyncService:
    """사이트 설정 + 전송 이력을 포터블 JSON으로 pull/push 합니다."""

    def __init__(
        self,
        config_manager: ConfigManager,
        db: SyncHistoryDb,
        logger: Optional[logging.Logger] = None,
    ):
        self.config_manager = config_manager
        self.db = db
        self.logger = logger or logging.getLogger("websync.backup")
        self._lock = threading.Lock()
        self.last_result: dict[str, Any] = {}

    def _load_config(self) -> dict:
        return self.config_manager.load_config()

    def _backup_cfg(self, config: dict | None = None) -> dict:
        cfg = config if config is not None else self._load_config()
        bs = cfg.get("backup_sync")
        return bs if isinstance(bs, dict) else {}

    def get_folder(self, config: dict | None = None) -> str:
        folder = (self._backup_cfg(config).get("folder") or "").strip()
        if not folder:
            return ""
        return resolve_path(folder)

    def is_enabled(self, config: dict | None = None) -> bool:
        return bool(self._backup_cfg(config).get("enabled"))

    def is_configured(self, config: dict | None = None) -> bool:
        cfg = config if config is not None else self._load_config()
        return self.is_enabled(cfg) and bool(self.get_folder(cfg))

    def _update_backup_meta(self, config: dict, **kwargs) -> dict:
        bs = config.setdefault("backup_sync", {})
        if not isinstance(bs, dict):
            bs = {}
            config["backup_sync"] = bs
        bs.update(kwargs)
        return config

    def pull(self, *, force: bool = False) -> dict[str, Any]:
        """클라우드 폴더 → 로컬 병합.

        force=True 이면 enabled 여부와 관계없이 folder만 있으면 수행 (수동 동기화용).
        """
        with self._lock:
            return self._pull_unlocked(force=force)

    def push(self, *, force: bool = False) -> dict[str, Any]:
        """로컬 → 클라우드 폴더 기록."""
        with self._lock:
            return self._push_unlocked(force=force)

    def sync_now(self) -> dict[str, Any]:
        """양방향: pull 후 push."""
        with self._lock:
            pull_result = self._pull_unlocked(force=True)
            push_result = self._push_unlocked(force=True)
            result = {
                "ok": pull_result.get("ok", False) and push_result.get("ok", False),
                "pull": pull_result,
                "push": push_result,
            }
            self.last_result = result
            return result

    def _acquire_folder_lock(self, folder: str) -> ProcessFileLock | None:
        lock = ProcessFileLock(os.path.join(folder, LOCK_FILENAME))
        if lock.acquire(blocking=False):
            return lock
        return None

    def _pull_unlocked(self, *, force: bool = False) -> dict[str, Any]:
        config = self._load_config()
        bs = self._backup_cfg(config)
        folder = self.get_folder(config)
        result: dict[str, Any] = {
            "ok": False,
            "action": "pull",
            "sites_changed": False,
            "sites_added": 0,
            "history_changed": 0,
            "skipped": False,
            "message": "",
        }

        if not folder:
            result["skipped"] = True
            result["message"] = "백업 폴더가 설정되지 않았습니다."
            self.last_result = result
            return result
        if not force and not bs.get("enabled"):
            result["skipped"] = True
            result["message"] = "백업 동기화가 비활성화되어 있습니다."
            self.last_result = result
            return result

        file_lock = self._acquire_folder_lock(folder)
        if file_lock is None:
            result["skipped"] = True
            result["message"] = "다른 프로세스가 백업 폴더를 사용 중입니다."
            self.logger.warning(result["message"])
            self.last_result = result
            return result

        try:
            sites_path = os.path.join(folder, SITES_FILENAME)
            history_path = os.path.join(folder, HISTORY_FILENAME)

            # --- sites ---
            remote_sites_payload = read_json_safe(sites_path)
            remote_sites, remote_sites_at = extract_sites(remote_sites_payload)
            local_sites = config.get("sites") if isinstance(config.get("sites"), list) else []
            last_sites_push = bs.get("last_sites_push_at")
            remote_wins = is_remote_newer(remote_sites_at, last_sites_push if isinstance(last_sites_push, str) else None)

            if remote_sites:
                before_urls = {
                    (s.get("url") or "").strip().lower()
                    for s in local_sites
                    if isinstance(s, dict) and s.get("url")
                }
                merged = merge_sites(
                    local_sites,
                    remote_sites,
                    remote_wins_same_url=remote_wins,
                )
                after_urls = {
                    (s.get("url") or "").strip().lower()
                    for s in merged
                    if isinstance(s, dict) and s.get("url")
                }
                added = len(after_urls - before_urls)
                # 내용 변경 감지 (길이 또는 remote wins 적용)
                if merged != local_sites:
                    expected_rev = config.get("_config_revision")
                    try:
                        expected_i = int(expected_rev) if expected_rev is not None else None
                    except (TypeError, ValueError):
                        expected_i = None

                    def _apply_sites(cfg: dict) -> None:
                        # RMW: 디스크 최신 사이트와 다시 병합
                        cur = cfg.get("sites") if isinstance(cfg.get("sites"), list) else []
                        cfg["sites"] = merge_sites(
                            cur, remote_sites, remote_wins_same_url=remote_wins
                        )

                    try:
                        config = self.config_manager.update_config(_apply_sites)
                    except Exception:
                        config["sites"] = merged
                        self.config_manager.save_config(
                            config, expected_revision=expected_i
                        )
                        config = self._load_config()
                    result["sites_changed"] = True
                    result["sites_added"] = added
                    bs = self._backup_cfg(config)

            # --- history ---
            history_changed = 0
            if bs.get("include_history", True):
                remote_hist_payload = read_json_safe(history_path)
                remote_posts, _ = extract_posts(remote_hist_payload)
                if remote_posts:
                    try:
                        history_changed = self.db.import_posts_union(remote_posts)
                    except SyncHistoryDbError as e:
                        result["message"] = f"이력 가져오기 실패: {e}"
                        self.logger.error(result["message"])
                        self.last_result = result
                        return result
            result["history_changed"] = history_changed

            result["ok"] = True
            parts = []
            if result["sites_changed"]:
                parts.append(f"사이트 병합(+{result['sites_added']})")
            if history_changed:
                parts.append(f"이력 {history_changed}건 반영")
            if not parts:
                parts.append("변경 없음")
            result["message"] = "가져오기 완료: " + ", ".join(parts)
            self.logger.info(result["message"])
            self.last_result = result
            return result
        except Exception as e:
            result["message"] = f"가져오기 실패: {e}"
            self.logger.exception(result["message"])
            self.last_result = result
            return result
        finally:
            file_lock.release()

    def _push_unlocked(self, *, force: bool = False) -> dict[str, Any]:
        config = self._load_config()
        bs = self._backup_cfg(config)
        folder = self.get_folder(config)
        result: dict[str, Any] = {
            "ok": False,
            "action": "push",
            "sites_written": False,
            "history_written": False,
            "history_count": 0,
            "skipped": False,
            "message": "",
        }

        if not folder:
            result["skipped"] = True
            result["message"] = "백업 폴더가 설정되지 않았습니다."
            self.last_result = result
            return result
        if not force and not bs.get("enabled"):
            result["skipped"] = True
            result["message"] = "백업 동기화가 비활성화되어 있습니다."
            self.last_result = result
            return result
        if not force and not bs.get("auto_export", True):
            result["skipped"] = True
            result["message"] = "자동 내보내기가 비활성화되어 있습니다."
            self.last_result = result
            return result

        file_lock = self._acquire_folder_lock(folder)
        if file_lock is None:
            result["skipped"] = True
            result["message"] = "다른 프로세스가 백업 폴더를 사용 중입니다."
            self.logger.warning(result["message"])
            self.last_result = result
            return result

        try:
            ensure_dir(folder)
            exported_at = now_iso()
            components: list[str] = []

            # sites — 시크릿/로컬 경로 없이 sites만
            sites = config.get("sites") if isinstance(config.get("sites"), list) else []
            sites_payload = build_sites_payload(sites, exported_at=exported_at)
            write_json_atomic(os.path.join(folder, SITES_FILENAME), sites_payload)
            result["sites_written"] = True
            components.append("sites")

            # history
            if bs.get("include_history", True):
                try:
                    posts = self.db.export_all_posts()
                except SyncHistoryDbError as e:
                    result["message"] = f"이력 내보내기 실패: {e}"
                    self.logger.error(result["message"])
                    self.last_result = result
                    return result
                # push 전 remote와 union 해서 쓴다 (다른 PC 이력 보존)
                remote_payload = read_json_safe(os.path.join(folder, HISTORY_FILENAME))
                remote_posts, _ = extract_posts(remote_payload)
                if remote_posts:
                    try:
                        self.db.import_posts_union(remote_posts)
                        posts = self.db.export_all_posts()
                    except SyncHistoryDbError as e:
                        self.logger.warning(f"push 전 이력 병합 실패(로컬만 기록): {e}")
                hist_payload = build_history_payload(posts, exported_at=exported_at)
                write_json_atomic(os.path.join(folder, HISTORY_FILENAME), hist_payload)
                result["history_written"] = True
                result["history_count"] = len(posts)
                components.append("synced_posts")

            write_json_atomic(
                os.path.join(folder, MANIFEST_FILENAME),
                build_manifest(exported_at=exported_at, components=components),
            )

            # 메타 기록 (LWW 기준) — RMW 로 다른 설정 덮어쓰기 방지
            hist_written = result["history_written"]
            prev_hist = bs.get("last_history_push_at", "")

            def _apply_meta(cfg: dict) -> None:
                self._update_backup_meta(
                    cfg,
                    last_sites_push_at=exported_at,
                    last_history_push_at=exported_at if hist_written else prev_hist,
                    last_sync_at=exported_at,
                    last_sync_message=f"내보내기 완료 ({exported_at})",
                )

            self.config_manager.update_config(_apply_meta)

            result["ok"] = True
            result["message"] = (
                f"내보내기 완료: 사이트 {len(sites)}개"
                + (f", 이력 {result['history_count']}건" if result["history_written"] else "")
            )
            self.logger.info(result["message"])
            self.last_result = result
            return result
        except Exception as e:
            result["message"] = f"내보내기 실패: {e}"
            self.logger.exception(result["message"])
            self.last_result = result
            return result
        finally:
            file_lock.release()
