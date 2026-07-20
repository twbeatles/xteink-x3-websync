import sqlite3
import os
import threading
from websync.core.paths import PROJECT_ROOT, resolve_path

LEGACY_DEVICE_IP = "*"


class SyncHistoryDbError(Exception):
    """동기화 이력 DB 접근 실패"""


class SyncHistoryDb:
    """기기별 동기화 이력을 관리하는 SQLite DB 클래스"""
    _db_lock = threading.Lock()

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            self.db_path = os.path.join(PROJECT_ROOT, "sync_history.db")
        else:
            self.db_path = resolve_path(db_path)
        self._init_db()

    def _connect(self):
        return sqlite3.connect(self.db_path, timeout=10.0)

    def _init_db(self):
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name='synced_posts'"
                    )
                    if cursor.fetchone():
                        cursor.execute("PRAGMA table_info(synced_posts)")
                        columns = {row[1] for row in cursor.fetchall()}
                        if "device_ip" not in columns:
                            self._migrate_legacy_schema(conn)
                    else:
                        self._create_v2_table(conn)
                    conn.commit()
            except SyncHistoryDbError:
                raise
            except Exception as e:
                raise SyncHistoryDbError(f"DB 초기화 실패: {e}") from e

    @staticmethod
    def _create_v2_table(conn: sqlite3.Connection):
        conn.execute("""
            CREATE TABLE IF NOT EXISTS synced_posts (
                url TEXT NOT NULL,
                device_ip TEXT NOT NULL,
                site_name TEXT,
                title TEXT,
                synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (url, device_ip)
            )
        """)

    def _migrate_legacy_schema(self, conn: sqlite3.Connection):
        conn.execute("ALTER TABLE synced_posts RENAME TO synced_posts_legacy")
        self._create_v2_table(conn)
        conn.execute("""
            INSERT INTO synced_posts (url, device_ip, site_name, title, synced_at)
            SELECT url, ?, site_name, title, synced_at FROM synced_posts_legacy
        """, (LEGACY_DEVICE_IP,))
        conn.execute("DROP TABLE synced_posts_legacy")

    def is_synced_for_device(self, url: str, device_ip: str) -> bool:
        """특정 기기에 해당 URL이 이미 전송되었는지 확인합니다.

        레거시 device_ip='*' 행은 더 이상 모든 기기에 대한 완료로 취급하지 않습니다.
        (다중 기기 도입 후 재전송이 막히던 문제 수정)
        """
        if not url or not device_ip:
            return False
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT 1 FROM synced_posts
                        WHERE url = ? AND device_ip = ?
                        """,
                        (url, device_ip),
                    )
                    return cursor.fetchone() is not None
            except Exception as e:
                raise SyncHistoryDbError(f"DB 조회 실패: {e}") from e

    def needs_sync(self, url: str, target_ips: list[str]) -> bool:
        """하나라도 미전송 기기가 있으면 True."""
        if not url:
            return False
        if not target_ips:
            return not self.is_synced(url)
        return any(not self.is_synced_for_device(url, ip) for ip in target_ips)

    def pending_device_ips(self, url: str, target_ips: list[str]) -> list[str]:
        """아직 전송되지 않은 기기 IP 목록."""
        if not url:
            return []
        if not target_ips:
            return [] if self.is_synced(url) else []
        return [ip for ip in target_ips if not self.is_synced_for_device(url, ip)]

    def is_synced(self, url: str) -> bool:
        """URL에 동기화 이력이 존재하는지 (레거시·기기별 포함)."""
        if not url:
            return False
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM synced_posts WHERE url = ? LIMIT 1", (url,))
                    return cursor.fetchone() is not None
            except Exception as e:
                raise SyncHistoryDbError(f"DB 조회 실패: {e}") from e

    def mark_synced(self, url: str, site_name: str, title: str, device_ip: str):
        """특정 기기에 대한 전송 완료 이력을 저장합니다."""
        self.mark_synced_many(
            [{"url": url, "site_name": site_name, "title": title, "device_ip": device_ip}]
        )

    def mark_synced_many(self, entries: list[dict]) -> int:
        """여러 전송 완료 이력을 한 트랜잭션으로 저장합니다.

        entries: [{url, site_name, title, device_ip}, ...]
        Returns: 저장된 행 수
        """
        if not entries:
            return 0
        rows = []
        for e in entries:
            if not isinstance(e, dict):
                continue
            url = (e.get("url") or "").strip()
            device_ip = (e.get("device_ip") or "").strip()
            if not url or not device_ip:
                continue
            rows.append(
                (
                    url,
                    device_ip,
                    e.get("site_name") or "",
                    e.get("title") or "",
                )
            )
        if not rows:
            return 0
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.executemany(
                        """
                        INSERT OR REPLACE INTO synced_posts (url, device_ip, site_name, title)
                        VALUES (?, ?, ?, ?)
                        """,
                        rows,
                    )
                    conn.commit()
                    return len(rows)
            except Exception as e:
                raise SyncHistoryDbError(f"DB 기록 저장 실패: {e}") from e

    def remap_legacy_star_to_device(self, device_ip: str) -> int:
        """레거시 device_ip='*' 행을 지정 기기 IP로 이관합니다. Returns: 갱신 건수."""
        if not device_ip or device_ip == LEGACY_DEVICE_IP:
            return 0
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    # 이미 동일 URL+device 가 있으면 * 행만 삭제, 없으면 IP 로 변경
                    cursor.execute(
                        "SELECT url, site_name, title, synced_at FROM synced_posts WHERE device_ip = ?",
                        (LEGACY_DEVICE_IP,),
                    )
                    legacy = cursor.fetchall()
                    changed = 0
                    for url, site_name, title, synced_at in legacy:
                        cursor.execute(
                            "SELECT 1 FROM synced_posts WHERE url = ? AND device_ip = ?",
                            (url, device_ip),
                        )
                        if cursor.fetchone():
                            cursor.execute(
                                "DELETE FROM synced_posts WHERE url = ? AND device_ip = ?",
                                (url, LEGACY_DEVICE_IP),
                            )
                        else:
                            cursor.execute(
                                """
                                UPDATE synced_posts SET device_ip = ?
                                WHERE url = ? AND device_ip = ?
                                """,
                                (device_ip, url, LEGACY_DEVICE_IP),
                            )
                        changed += 1
                    conn.commit()
                    return changed
            except Exception as e:
                raise SyncHistoryDbError(f"레거시 이력 이관 실패: {e}") from e

    def get_history(self, limit: int = 200) -> list:
        """동기화 이력을 최신순으로 반환 (URL 기준 집계)."""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT url, site_name, title, MAX(synced_at), GROUP_CONCAT(device_ip)
                        FROM synced_posts
                        GROUP BY url
                        ORDER BY MAX(synced_at) DESC
                        LIMIT ?
                        """,
                        (limit,),
                    )
                    return cursor.fetchall()
            except Exception as e:
                raise SyncHistoryDbError(f"DB 이력 조회 실패: {e}") from e

    def delete_entry(self, url: str):
        """특정 URL의 모든 기기 동기화 이력 삭제 (재전송 허용)."""
        if not url:
            return
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM synced_posts WHERE url = ?", (url,))
                    conn.commit()
            except Exception as e:
                raise SyncHistoryDbError(f"DB 이력 삭제 실패: {e}") from e

    def clear_all(self):
        """모든 동기화 이력 초기화"""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM synced_posts")
                    conn.commit()
            except Exception as e:
                raise SyncHistoryDbError(f"DB 전체 초기화 실패: {e}") from e

    def get_count(self) -> int:
        """고유 URL 이력 건수 반환"""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(DISTINCT url) FROM synced_posts")
                    row = cursor.fetchone()
                    return row[0] if row else 0
            except Exception as e:
                raise SyncHistoryDbError(f"DB 건수 조회 실패: {e}") from e

    def export_all_posts(self) -> list[dict]:
        """전체 전송 이력을 dict 목록으로 반환 (백업/클라우드 동기화용)."""
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT url, device_ip, site_name, title, synced_at
                        FROM synced_posts
                        ORDER BY synced_at ASC, url ASC, device_ip ASC
                        """
                    )
                    rows = cursor.fetchall()
                    return [
                        {
                            "url": row[0] or "",
                            "device_ip": row[1] or "",
                            "site_name": row[2] or "",
                            "title": row[3] or "",
                            "synced_at": row[4] or "",
                        }
                        for row in rows
                    ]
            except Exception as e:
                raise SyncHistoryDbError(f"DB 이력 내보내기 실패: {e}") from e

    def import_posts_union(self, posts: list[dict]) -> int:
        """원격 이력을 합집합 병합합니다. (url, device_ip) 기준.

        - 없으면 INSERT
        - 있으면 synced_at 이 더 최신인 쪽의 title/site_name/synced_at 유지
        Returns:
            신규 삽입 또는 갱신된 행 수
        """
        if not posts:
            return 0
        changed = 0
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    for post in posts:
                        if not isinstance(post, dict):
                            continue
                        url = (post.get("url") or "").strip()
                        device_ip = (post.get("device_ip") or "").strip()
                        if not url or not device_ip:
                            continue
                        site_name = post.get("site_name") or ""
                        title = post.get("title") or ""
                        synced_at = post.get("synced_at") or ""

                        cursor.execute(
                            """
                            SELECT site_name, title, synced_at FROM synced_posts
                            WHERE url = ? AND device_ip = ?
                            """,
                            (url, device_ip),
                        )
                        existing = cursor.fetchone()
                        if existing is None:
                            if synced_at:
                                cursor.execute(
                                    """
                                    INSERT INTO synced_posts
                                    (url, device_ip, site_name, title, synced_at)
                                    VALUES (?, ?, ?, ?, ?)
                                    """,
                                    (url, device_ip, site_name, title, synced_at),
                                )
                            else:
                                cursor.execute(
                                    """
                                    INSERT INTO synced_posts
                                    (url, device_ip, site_name, title)
                                    VALUES (?, ?, ?, ?)
                                    """,
                                    (url, device_ip, site_name, title),
                                )
                            changed += 1
                            continue

                        old_site, old_title, old_at = existing
                        old_at_s = old_at or ""
                        new_at_s = synced_at or ""
                        # 원격이 더 최신이거나 로컬 시각이 비어 있으면 갱신
                        # ISO(T) / SQLite(공백) 혼용을 위해 비교용 정규화
                        old_cmp = old_at_s.replace("T", " ", 1)
                        new_cmp = new_at_s.replace("T", " ", 1)
                        if new_at_s and (not old_at_s or new_cmp > old_cmp):
                            cursor.execute(
                                """
                                UPDATE synced_posts
                                SET site_name = ?, title = ?, synced_at = ?
                                WHERE url = ? AND device_ip = ?
                                """,
                                (site_name or old_site, title or old_title, new_at_s, url, device_ip),
                            )
                            changed += 1
                        elif not old_at_s and not new_at_s:
                            # 둘 다 시각 없음: 메타만 보강
                            if (site_name and site_name != old_site) or (title and title != old_title):
                                cursor.execute(
                                    """
                                    UPDATE synced_posts
                                    SET site_name = COALESCE(NULLIF(?, ''), site_name),
                                        title = COALESCE(NULLIF(?, ''), title)
                                    WHERE url = ? AND device_ip = ?
                                    """,
                                    (site_name, title, url, device_ip),
                                )
                                if cursor.rowcount:
                                    changed += 1
                    conn.commit()
                    return changed
            except Exception as e:
                raise SyncHistoryDbError(f"DB 이력 가져오기 실패: {e}") from e
