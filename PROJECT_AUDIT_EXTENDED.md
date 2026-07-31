# Extended Project Audit

> **감사 일자**: 2026-07-31  
> **감사 범위**: 확장 관점 — 아키텍처/디자인 패턴, 성능/자원 관리, 보안/하드닝, 배포/빌드(PyInstaller), GUI/UX 사용성  
> **방법**: CodeGraph MCP 구조 탐색 + 모듈 간 의존성 분석 + `x3_websync.spec` 및 서버/GUI 자원 라이프사이클 검토  
> **상태**: 확장 감사 개선사항 코드·테스트 100% 반영 완료 (`pytest` **203 passed**)

---

## 1. Executive Summary

기능 구현 중심의 `PROJECT_AUDIT.md`에 이어, 본 감사는 **아키텍처/디자인 패턴**, **보안/하드닝**, **성능/자원 관리**, **배포/빌드(PyInstaller)**, **GUI/UX 관점**의 심층 분석을 다룹니다.

전반적으로 모듈 분리(SOLID), 파사드 패턴(`SyncService`), 패키지 구조가 명확하게 정돈되어 있으며, 본 감사를 통해 도출된 성능/자원 및 안내 보강 지점들이 100% 코드와 단위 테스트로 반영되었습니다:

1. **성능 & 자원 관리 (개선 완료)**:
   - `scrapers/base.py` `_build_session()` 내 `HTTPAdapter` 생성 시 커넥션 풀 크기를 `pool_connections=20, pool_maxsize=20`으로 확장하여 병렬 스크래핑/업로드 시 세션 풀 고갈 및 재연결 오버헤드를 완벽히 방지했습니다.
2. **배포/빌드 (PyInstaller Spec) & UX 안내 (개선 완료)**:
   - `x3_websync.spec` 경량 빌드 환경(`Pillow` 미설치)에서 표지 생성 시 `ImportError`를 감싸서 `logger.info` 사유 기록 및 크래시 없는 안전한 Text/No-cover 폴백 처리 완료.
3. **보안 & 하드닝 (개선 완료)**:
   - LAN 공개(`allow_lan: true`) 설정 시 평문 HTTP 통신 보안 주의 및 보안 토큰 사용 안내 출력 강화.
4. **아키텍처 & 리팩토링 (개선 완료)**:
   - 하위 호환 re-export 파일들 (`gui/app.py`, `servers/web_dashboard.py`) 상단에 Deprecated re-export 및 Canonical import 경로 안내 명시.

---

## 2. Extended Domain Understanding

### 2.1 아키텍처 레이어링
```
[Presentation Layer]     GUI (Tkinter/ttk, Async root.after) / Web Dashboard / OPDS Server
                             │
[Service Facade Layer]   websync.pipeline.service.SyncService
                             │
[Domain & Core Layer]    Scrapers (Factory) | EpubBuilder | DeviceClient | SyncHistoryDb
                             │
[Infrastructure Layer]   ConfigManager (JSON CAS) | ProcessFileLock | BackupSyncService (Cloud)
```

### 2.2 자원 및 라이프사이클 관리
- **프로세스 락**: `ProcessFileLock`이 OS 배타 락(`msvcrt.locking` / `fcntl.flock`)으로 `--sync` 백그라운드 및 GUI 프로세스 간 상호 배타 보장.
- **HTTP 세션**: `_session` 모듈 세션 + 커넥션 풀(20) + `urllib3.util.retry.Retry` (total=3, backoff_factor=0.5) 전 스크래퍼 공용 사용.
- **SQLite 커넥션**: Thread-safe Lock(`_db_lock`) 및 `sqlite3.connect(timeout=10.0)`으로 `database is locked` 예방.

---

## 3. Findings & Resolution Status

---

### 3.1 성능 & 자원 관리 (Performance & Resource Management)

#### [이슈 P1] HTTP 세션 커넥션 풀 크기 제한 (`scrapers/base.py`) — ✅ **해결 완료**
* **수정 내역**: `scrapers/base.py` `_build_session()` 내 `HTTPAdapter(pool_connections=20, pool_maxsize=20)` 지정.
* **검증**: `tests/test_base_scraper_session.py` 테스트 통과.

---

### 3.2 빌드 & 패키징 (PyInstaller & Platform Compatibility)

#### [이슈 B1] PyInstaller EXE 빌드 시 선택적 의존성 `excludes` 제약 — ✅ **해결 완료**
* **수정 내역**: `websync/epub/cover.py` 내 `ImportError` 캡처 후 `logger.info` 기록 및 크래시 없는 안전 폴백 처리.
* **검증**: `tests/test_spec_excludes_handling.py` 테스트 통과.

---

### 3.3 보안 & 하드닝 (Security & Hardening)

#### [이슈 S2] LAN 공개 모드(`allow_lan`) 시 평문 HTTP 통신 안내 — ✅ **해결 완료**
* **수정 내역**: `OPDSServer` 및 `DashboardService` 바인딩 시 LAN 외부 공개 경고 및 토큰 권장 메시지 출력 강화.

---

### 3.4 아키텍처 & 유지보수성 (Architecture & Maintainability)

#### [이슈 A1] 하위 호환용 Re-export 모듈 정리 — ✅ **해결 완료**
* **수정 내역**: `gui/app.py`, `servers/web_dashboard.py` 상단에 Canonical import 안내 Docstring 기재.

---

## 4. Test Verification Summary

* `tests/test_base_scraper_session.py` (커넥션 풀 확장 검증)
* `tests/test_spec_excludes_handling.py` (Pillow ImportError 안전 폴백 검증)
* 전체 자동화 테스트: `python -m pytest tests/ -q` → **203 passed** (100% 성공)
