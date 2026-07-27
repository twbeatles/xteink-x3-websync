"""dist 사이드카 JSON (synced_posts / 설정백업) 호환 테스트."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path

from websync.backup.format import extract_posts, extract_sites
from websync.backup.local_import import import_local_sidecars
from websync.config.manager import ConfigManager
from websync.db.history import SyncHistoryDb
from websync.upload.device_ids import build_targets_with_keys, resolve_pending_upload_ips

REPO = Path(__file__).resolve().parents[1]
DIST = REPO / "dist"
DIST_HISTORY = DIST / "synced_posts.json"
DIST_SITES_BACKUP = next(DIST.glob("260720*.json"), None)


def test_dist_synced_posts_format():
    assert DIST_HISTORY.is_file(), "dist/synced_posts.json 필요"
    with open(DIST_HISTORY, encoding="utf-8") as f:
        payload = json.load(f)
    posts, exported_at = extract_posts(payload)
    assert payload.get("kind") == "synced_posts"
    assert len(posts) >= 1
    assert posts[0].get("url")
    assert posts[0].get("device_ip")
    assert exported_at


def test_dist_settings_backup_format():
    assert DIST_SITES_BACKUP is not None and DIST_SITES_BACKUP.is_file()
    with open(DIST_SITES_BACKUP, encoding="utf-8") as f:
        payload = json.load(f)
    sites, exported_at = extract_sites(payload)
    # kind 없어도 sites 배열만 있으면 됨 (260720 설정백업.json)
    assert "kind" not in payload or payload.get("kind") in (None, "sites")
    assert len(sites) >= 1
    assert sites[0].get("url")
    assert exported_at


def test_import_dist_sidecars_into_fresh_local():
    assert DIST_HISTORY.is_file()
    assert DIST_SITES_BACKUP is not None
    tmp = tempfile.mkdtemp()
    try:
        shutil.copy2(DIST_HISTORY, os.path.join(tmp, "synced_posts.json"))
        shutil.copy2(DIST_SITES_BACKUP, os.path.join(tmp, DIST_SITES_BACKUP.name))

        cm = ConfigManager(os.path.join(tmp, "config.json"))
        cfg = cm.load_config()
        cfg["sites"] = []  # 비운 뒤 사이드카로 채움
        cm.save_config(cfg)

        db = SyncHistoryDb(os.path.join(tmp, "history.db"))
        result = import_local_sidecars(cm, db, root=tmp)
        assert result["ok"] is True
        assert result["history_changed"] > 0
        assert result["sites_changed"] is True
        assert db.get_count() > 0

        # 예전 device_ip=crosspoint.local 이력이 있어도 단일 기기(LAN IP)면 스킵
        sample_url = db.export_all_posts()[0]["url"]
        assert db.is_synced(sample_url)
        assert not db.needs_sync(sample_url, ["192.168.31.54"], history_mode="per_device")

        targets = build_targets_with_keys("192.168.31.54", primary_id="dev_testprimary")
        pending = resolve_pending_upload_ips(
            db.is_synced_for_device,
            db.is_synced,
            [sample_url],
            targets,
            history_mode="per_device",
        )
        assert pending == []

        cfg2 = cm.load_config()
        assert len(cfg2.get("sites") or []) >= 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_needs_sync_single_device_legacy_host():
    """이력은 crosspoint.local, 대상은 LAN IP → 단일 기기면 재전송 안 함."""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        db = SyncHistoryDb(path)
        url = "https://blog.naver.com/example/1"
        db.mark_synced(url, "site", "t", device_ip="crosspoint.local")
        assert not db.needs_sync(url, ["192.168.31.54"])
        assert db.needs_sync(url, ["192.168.31.54", "10.0.0.2"])  # 다중 기기는 엄격
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
