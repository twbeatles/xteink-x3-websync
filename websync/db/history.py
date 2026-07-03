import sqlite3
import os
import threading
from websync.core.paths import PROJECT_ROOT, resolve_path


class SyncHistoryDbError(Exception):
    """동기화 이력 DB 접근 실패"""


class SyncHistoryDb:
    """이미 기기로 전송(동기화) 완료된 게시글/포스트 이력을 관리하는 SQLite DB 클래스"""
    _db_lock = threading.Lock() # 스레드 간 DB 접근 Race Condition 차단을 위한 락

    def __init__(self, db_path: str | None = None):
        if db_path is None:
            self.db_path = os.path.join(PROJECT_ROOT, "sync_history.db")
        else:
            self.db_path = resolve_path(db_path)
        self._init_db()

    def _init_db(self):
        with self._db_lock:
            try:
                # timeout 10초를 주어 database locked 리스크 최소화
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        CREATE TABLE IF NOT EXISTS synced_posts (
                            url TEXT PRIMARY KEY,
                            site_name TEXT,
                            title TEXT,
                            synced_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                        )
                    """)
                    conn.commit()
            except Exception as e:
                print(f"❌ DB 초기화 실패: {e}")

    def is_synced(self, url: str) -> bool:
        """해당 포스트 URL이 이미 동기화(전송)되었는지 여부 확인"""
        if not url:
            return False
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT 1 FROM synced_posts WHERE url = ?", (url,))
                    return cursor.fetchone() is not None
            except Exception as e:
                raise SyncHistoryDbError(f"DB 조회 실패: {e}") from e

    def mark_synced(self, url: str, site_name: str, title: str):
        """포스트 전송 완료 후 이력 테이블에 저장"""
        if not url:
            return
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT OR REPLACE INTO synced_posts (url, site_name, title)
                        VALUES (?, ?, ?)
                    """, (url, site_name, title))
                    conn.commit()
            except Exception as e:
                print(f"❌ DB 기록 저장 실패: {e}")

    def get_history(self, limit: int = 200) -> list:
        """동기화 이력을 최신순으로 반환 (GUI 이력 탭 표시용)"""
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT url, site_name, title, synced_at FROM synced_posts ORDER BY synced_at DESC LIMIT ?",
                        (limit,)
                    )
                    return cursor.fetchall()
            except Exception as e:
                print(f"⚠️ DB 이력 조회 실패: {e}")
                return []

    def delete_entry(self, url: str):
        """특정 URL의 동기화 이력 삭제 (재전송 허용)"""
        if not url:
            return
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM synced_posts WHERE url = ?", (url,))
                    conn.commit()
            except Exception as e:
                print(f"❌ DB 이력 삭제 실패: {e}")

    def clear_all(self):
        """모든 동기화 이력 초기화"""
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("DELETE FROM synced_posts")
                    conn.commit()
            except Exception as e:
                print(f"❌ DB 전체 초기화 실패: {e}")

    def get_count(self) -> int:
        """전체 이력 건수 반환"""
        with self._db_lock:
            try:
                with sqlite3.connect(self.db_path, timeout=10.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT COUNT(*) FROM synced_posts")
                    row = cursor.fetchone()
                    return row[0] if row else 0
            except Exception:
                return 0
