import sqlite3
import os

class SyncHistoryDb:
    """이미 기기로 전송(동기화) 완료된 게시글/포스트 이력을 관리하는 SQLite DB 클래스"""
    def __init__(self, db_path="sync_history.db"):
        self.db_path = db_path
        self._init_db()

    def _init_db(self):
        try:
            with sqlite3.connect(self.db_path) as conn:
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
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT 1 FROM synced_posts WHERE url = ?", (url,))
                return cursor.fetchone() is not None
        except Exception as e:
            print(f"⚠️ DB 조회 실패: {e}")
            return False

    def mark_synced(self, url: str, site_name: str, title: str):
        """포스트 전송 완료 후 이력 테이블에 저장"""
        if not url:
            return
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO synced_posts (url, site_name, title)
                    VALUES (?, ?, ?)
                """, (url, site_name, title))
                conn.commit()
        except Exception as e:
            print(f"❌ DB 기록 저장 실패: {e}")
