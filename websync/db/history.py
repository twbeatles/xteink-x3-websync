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
        """특정 기기에 해당 URL이 이미 전송되었는지 확인합니다."""
        if not url or not device_ip:
            return False
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        SELECT 1 FROM synced_posts
                        WHERE url = ? AND (device_ip = ? OR device_ip = ?)
                        """,
                        (url, device_ip, LEGACY_DEVICE_IP),
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
        if not url or not device_ip:
            return
        with self._db_lock:
            try:
                with self._connect() as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        """
                        INSERT OR REPLACE INTO synced_posts (url, device_ip, site_name, title)
                        VALUES (?, ?, ?, ?)
                        """,
                        (url, device_ip, site_name, title),
                    )
                    conn.commit()
            except Exception as e:
                raise SyncHistoryDbError(f"DB 기록 저장 실패: {e}") from e

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
