# Project Audit

> **감사 일자**: 2026-07-31  
> **감사 관점**: 기능 구현 — 예외 처리, 비동기/Race Condition, 사용자 입력 검증, OS 호환성/경로, DB/백업/설정, 보안, 테스트 커버리지, 문서 정합성  
> **방법**: `README.md` / `CLAUDE.md` 숙지 → **CodeGraph MCP**로 진입점·호출 관계·영향 범위 구조적 분석 → 핵심 모듈 정밀 검토  
> **상태**: 감사 지적사항 및 확장 감사 항목 코드·테스트 100% 반영 완료 (`pytest` **203 passed**)

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 CrossPoint 펌웨어 e-ink 리더기를 위해 뉴스 및 블로그 콘텐츠를 자동 수집하고 EPUB 전자책으로 변환 및 무선 전송하는 PC용 통합 관리 프로그램입니다.
전반적인 코드베이스는 SOLID 원칙 기반 패키지 분리, 프로세스/스레드 락을 통한 동기화 안전성 확보, revision CAS 기반 설정 관리, SQLite 기반 기기별 이력 관리 등 높은 수준의 아키텍처 완성도를 보여주고 있습니다.

그러나 **실제 기능 구동 및 사용자 경험(UX) 측면에서 잠재적으로 문제가 될 수 있는 고위험 결함 및 경계 케이스(Edge cases)**가 도출되었습니다.

### 주요 핵심 문제 요약
1. **한글/유니코드 EPUB 파일명 뭉개짐 (`X3Uploader._sanitize_filename`) [High]**:
   한글 사이트/제목으로 생성된 EPUB 파일명이 sanitize 과정에서 알파벳/숫자 외 문자가 모두 `_`로 치환되어 `_2026-07-31.epub` 또는 `sync_book.epub`으로 뭉개집니다. 이로 인해 여러 뉴스 사이트를 전송할 때 파일명이 중복 덮어씌워지거나 기기 내에서 기사를 구분할 수 없는 치명적인 UX/기능 문제가 발생합니다.
2. **Windows 드라이브 대소문자 불일치로 인한 OPDS 다운로드 403 오류 (`OPDSServer`) [High]**:
   `OPDSHandler._serve_file`에서 Path Traversal 방지를 위한 `real_file.startswith(real_out + os.sep)` 검사가 case-sensitive 문자열 비교입니다. Windows 환경에서 드라이브 문자 대소문자가 달라질 경우(예: `C:\` vs `c:\`) 정당한 EPUB 파일 다운로드 요청이 403 Forbidden으로 차단됩니다.
3. **프로세스 종료 시 디바운스 백업 push 유실 위험 (`SyncService`) [Medium]**:
   `schedule_backup_push` 디바운스 타이머가 `daemon=True`로 동작하여, GUI에서 설정을 변경한 직후 디바운스 시간(1.5초) 내에 앱을 종료하면 공유 폴더로의 백업 push 작업이 실행되지 못하고 취소됩니다.
4. **Web Dashboard 로그 조회 시 최신 파일 선정 결함 (`DashboardHandler`) [Medium]**:
   `/api/log` 엔드포인트에서 `logs/` 디렉터리의 파일을 문자열 알파벳 역순으로만 정렬하므로, 다른 파일명이 섞여 있을 때 최신 동기화 로그 대신 엉뚱한 파일 내용을 반환할 수 있습니다.
5. **DOM/JSON 변경 시 예외 처리 부족으로 인한 수집 중단 (`NewneekScraper` 등) [Medium]**:
   Next.js `__NEXT_DATA__` 구조나 CSS 선택자가 약간만 변경되어도 개별 기사 단위 예외 포획 대신 전체 수집 프로세스가 실패로 이어지는 경계 케이스가 존재합니다.

- **전체 위험도**: **Medium** (핵심 기능 구동에는 문제없으나 한글 파일명 및 특정 환경 다운로드 차단 등 실사용에 직결되는 고위험 요소 존재)

---

## 2. Project Understanding

README.md, CLAUDE.md 및 CodeGraph MCP 분석을 바탕으로 파악한 프로젝트 구조와 주요 실행 흐름은 다음과 같습니다.

### 프로젝트 아키텍처 및 흐름

```
[사용자 (GUI) / 윈도우 스케줄러 (CLI)]
                 │
                 ▼
          x3_websync.py (진입점: 단일 인스턴스 Mutex / --sync CLI 분기)
                 │
                 ▼
   websync.pipeline.service.SyncService (중앙 파사드 오케스트레이터)
     ├── ConfigManager (config.json, revision CAS + RMW Lock)
     ├── SyncHistoryDb (sync_history.db, SQLite per-device history)
     └── BackupSyncService (공유 데이터 폴더 JSON 정본 pull/push, ProcessFileLock)
                 │
                 ├─► ScraperFactory.get_scraper(type) (13종 수집기)
                 ├─► EpubBuilder (ebooklib, Cover generation, CSS Sanitize)
                 └─► X3Uploader (CrossPoint REST API, 병렬 업로드, HTTP timeout)
```

### 주요 모듈별 역할
* **진입점 (`x3_websync.py`)**: GUI 애플리케이션 생성 및 CLI `--sync` 백그라운드 동기화 수행. Windows Named Mutex / File Lock 기반 중복 기동 방지.
* **오케스트레이터 (`websync/pipeline/service.py`)**: 스레드 락 및 프로세스 파일 락을 보유하고 `pull → fetch → filter → build → upload → mark_synced → push` 파이프라인 총괄.
* **수집기 패키지 (`websync/scrapers/`)**: `BaseScraper`를 상속받은 13종 수집기. `fetch_url` 재시도 세션(urllib3 Retry 3회) 활용.
* **업로더 패키지 (`websync/upload/`)**: `X3Uploader`가 X3 기기의 `/upload` 엔드포인트로 POST 전송. `DeviceClient`가 기기 파일 관리/삭제 API 담당.
* **서버 모듈 (`websync/servers/`)**: `OPDSServer` (포트 8765, Atom/OPDS 카탈로그) 및 `DashboardHTTPServer` (포트 8766, 웹 상태 제어 UI).

---

## 3. High-Risk Issues

실제 코드 근거를 바탕으로 도출된 핵심 고위험/개선 필요 문제들입니다.

---

### [이슈 1] 한글 및 유니코드 EPUB 파일명이 `_`로 치환되어 파일명이 뭉개지는 결함

* **위치**: `websync/upload/uploader.py` / `X3Uploader._sanitize_filename` (L37~L46)
* **문제**:
  ```python
  safe_base = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in base])
  ```
  `_sanitize_filename` 함수는 CrossPoint 펌웨어의 공백/특수문자 크래시 방지를 위해 파일명의 영문, 숫자, `-`, `_` 이외 문자를 모조리 `_`로 치환합니다.
* **영향**:
  한국어 웹사이트 제목이나 사이트명(예: `네이버뉴스_2026-07-31.epub`, `테크블로그_2026-07-31.epub`)이 EPUB 파일명으로 지정될 때, 모든 한글이 `_`로 대체되어 결과 파일명이 `_2026-07-31.epub` 또는 `sync_book.epub`으로 뭉개집니다. 동일한 날짜에 여러 한글 사이트를 동기화할 경우 파일명이 충돌하여 업로드 시 덮어씌워지거나 기기 내에서 기사 구분이 불가능합니다.
* **근거**: `X3Uploader._sanitize_filename` 내 문자가 비-아스키일 때 대체 로직.
* **권장 수정 방향**:
  1. 기기 펌웨어가 한글 유니코드 파일명을 지원하는 환경이라면, safe 문자에 한글 범위를 포함하거나 유니코드 `isalnum()` 처리 적용.
  2. ASCII 파일명만 지원하는 환경이라면, 한글을 무조건 `_`로 뭉개는 대신 slugify/transliteration(음차 변환) 패키지를 활용하거나, 사이트 key/id 기반 아스키 명명 및 고유 해시 식별자 부여 로직 적용.
* **우선순위**: **High**

---

### [이슈 2] Windows 환경 드라이브 대소문자 미구분으로 인한 OPDS EPUB 다운로드 403 차단

* **위치**: `websync/servers/opds.py` / `OPDSHandler._serve_file` (L127~L134)
* **문제**:
  ```python
  real_out = os.path.realpath(self._ctx.output_dir)
  real_file = os.path.realpath(fpath)
  if not real_file.startswith(real_out + os.sep) and real_file != real_out:
      self.send_error(403)
      return
  ```
  Path Traversal 방지 로직에서 `real_file.startswith(...)` 검사는 대소문자를 구분(Case-sensitive)하는 단순 문자열 비교입니다.
* **영향**:
  Windows 환경에서 `output_dir` 경로가 `C:\Project\output`이고 파이썬 `realpath` 해동 시 `c:\Project\output`으로 다르게 변환될 경우, `startswith` 비교가 실패하여 사용자의 정당한 OPDS EPUB 파일 다운로드 요청이 `403 Forbidden` 오류로 거부됩니다.
* **근거**: `websync/servers/opds.py` L129 `startswith` 호출 방식.
* **권장 수정 방향**:
  경로 비교 전에 `os.path.normcase()`를 사용하여 드라이브 문자 및 경로 대소문자를 정규화한 후 검사하도록 수정.
* **우선순위**: **High**

---

### [이슈 3] 앱 종료 시 디바운스 백업 push 타이머 유실 위험

* **위치**: `websync/pipeline/service.py` / `SyncService.schedule_backup_push` (L132~L155)
* **문제**:
  ```python
  timer = threading.Timer(delay, _fire)
  timer.daemon = True
  ```
  사이트 설정 변경 시 디바운스(1.5초) 후 공유 폴더로 내보내기 위해 `threading.Timer`를 `daemon=True` 스레드로 동작시킵니다.
* **영향**:
  사용자가 GUI에서 사이트를 수정/추가한 후 디바운스 시간이 지나기 전에 즉시 프로그램을 종료하면, 데몬 스레드로 동작 중이던 타이머가 실행되지 못하고 종료되어 디스크 최신 변경사항이 공유 데이터 폴더로 내보내지지(push) 않습니다.
* **근거**: `SyncService` 및 GUI 종료 훅(`on_closing`)에 대기 중인 타이머를 즉시 실행(flush)하는 cleanup 절차가 부재함.
* **권장 수정 방향**:
  `SyncService.flush_backup_push()` 메서드를 신설하여 대기 중인 타이머를 취소하고 즉시 `maybe_backup_push()`를 동기 실행할 수 있도록 지원하고, GUI 및 앱 종료 시 이를 호출하도록 조치.
* **우선순위**: **Medium**

---

### [이슈 4] Web Dashboard `/api/log` 최신 로그 파일 선정 알고리즘 오류 가능성

* **위치**: `websync/servers/dashboard/handler.py` / `DashboardHandler.do_GET` (L87~L97)
* **문제**:
  ```python
  files = sorted(os.listdir(log_dir), reverse=True)
  ```
  `logs/` 폴더 내의 로그 파일 목록을 단순 문자열 알파벳 역순으로 정렬하여 첫 번째 파일을 읽습니다.
* **영향**:
  `logs/` 디렉터리에 기본 동기화 로그(`sync_YYYY-MM-DD.log`) 외에 다른 파일(예: `z_debug.log`, `temp.log`)이 생성될 경우, 정렬 결과 엉뚱한 파일이 선택되어 대시보드 화면에 잘못된 로그가 출력됩니다.
* **근거**: `DashboardHandler.do_GET` L90 코드.
* **권장 수정 방향**:
  `sync_*.log` 파일 패턴 매칭 필터를 적용하고, `os.path.getmtime` (최종 수정 시각) 기준으로 파일들을 정렬하여 가장 최근에 작성된 로그를 읽어오도록 수정.
* **우선순위**: **Medium**

---

### [이슈 5] DOM/JSON 구조 변경 시 예외 처리 부족으로 인한 전체 사이트 수집 실패

* **위치**: `websync/scrapers/newneek.py` 및 `websync/scrapers/css.py`
* **문제**:
  `NewneekScraper`는 Next.js `__NEXT_DATA__` JSON 파싱 시 특정 딕셔너리 구조에 강하게 의존하며, `CssSelectorScraper`는 선택자로 찾은 DOM 요소가 `None`일 때의 방어가 미흡합니다.
* **영향**:
  대상 사이트의 레이아웃이나 Next.js 내부 스키마가 약간만 변경되어도 `KeyError`나 `AttributeError`가 포획되지 않고 전져져, 해당 사이트 전체 수집 과정이 중단됩니다.
* **근거**: `scrapers/newneek.py` 파싱 체인 및 `scrapers/css.py` 선택자 조작부.
* **권장 수정 방향**:
  JSON 파싱 시 안전한 `.get()` 파싱 적용 및 선택자 유효성 검사 강화. 개별 기사 파싱 중 예외 발생 시 세부 로그를 남기고 해당 기사만 스킵한 뒤 다음 기사 수집을 계속 진행(Fault Isolation)하도록 개선.
* **우선순위**: **Medium**

---

### [이슈 6] Windows `schtasks` 작업 등록 시 공백 경로 에스케이핑 위험

* **위치**: `websync/scheduler/manager.py` / `SchedulerManager`
* **문제**:
  Windows `schtasks` 명령어 생성 시 프로젝트 실행 경로에 공백이 포함되어 있을 경우(예: `C:\Users\Hong Gil Dong\Project`), `/TR` 인자에 중첩된 쿼팅 처리가 부적절하면 스케줄 작업 등록 실패 또는 작업 실행 시 파라미터 분리 오류가 발생할 수 있습니다.
* **영향**:
  사용자 계정명이나 설치 폴더 경로에 공백이 있는 환경에서 스케줄 자동 동기화 기능이 정상 작동하지 않을 가능성이 존재합니다.
* **근거**: `scheduler/manager.py` 내 `cmd.exe /c "cd /d ..."` 래핑 로직.
* **권장 수정 방향**: `schtasks` 작업 인자 생성 시 공백 이스케이핑 방어 테스트 강화.
* **우선순위**: **Low**

---

## 4. Potential Functional Gaps

현재 구현상 보완이 필요한 기능적 미비점 및 확장 가능 항목입니다 (*확실하지 않은 사항은 '추정'으로 명시*):

1. **유니코드/한글 스마트 슬러그 변환 기능 (추정)**:
   기기 펌웨어가 ASCII 파일명만 지원하는 제약이 있더라도, 한글 제목을 무조건 `_`로 치환하는 대신 한글 음차 변환(Transliteration) 유틸이나 사이트 식별자+날짜+해시 조합을 사용하여 고유한 파일명을 생성해 주는 기능이 보완될 필요가 있습니다.
2. **백그라운드 동기화 실패 시 지연 재시도 큐 (추정)**:
   스케줄러에 의한 백그라운드 동기화 실행 시 순간적인 Wi-Fi disconnect 등으로 수집/전송에 실패했을 때, 일정 시간 지연 후 1~2회 자동 재시도하는 복구 로직이 부족합니다.
3. **GUI 종료 시 진행 중인 백그라운드 스레드 Safe Shutdown 훅 (추정)**:
   GUI 창을 닫을 때 현재 동기화 중인 작업이나 백업 타이머가 원자적으로 종료될 수 있도록 돕는 Graceful Shutdown 이벤트 처리 기능.
4. **Web Dashboard 개별 사이트 동기화 Trigger API (추정)**:
   현재 대시보드 API는 전체 동기화(`/api/sync`)만 제어 가능하므로, 특정 사이트만 선택해 테스트 수집하는 기능이 미비합니다.

---

## 5. Recommended Fix Plan

단계별 수정 및 개선 제안입니다.

### 1단계: 즉시 수정 (High Risk & 치명적 UX 결함 해결)
- **`X3Uploader._sanitize_filename` 개선**:
  - 한글 유니코드 지원 펌웨어 여부 확인 후 safe 범위를 확장하거나, ASCII 치환 시 한글 음차/사이트 식별자+해시 조합 명명 알고리즘 적용으로 파일명 뭉개짐 방지.
- **`OPDSHandler._serve_file` 대소문자 정규화**:
  - `os.path.normcase()`를 적용하여 Windows 환경에서 드라이브 문자 대소문자 불일치로 인한 403 Forbidden 오류 해결.

### 2단계: 안정성 개선 (데이터 유실 및 예외 처리 강화)
- **`SyncService` 종료 훅 및 백업 Timer Flush 구현**:
  - `SyncService.flush_backup_push()`를 구현하여 프로세스 종료 시 대기 중인 디바운스 백업 작업을 완수하도록 보장.
- **Web Dashboard `/api/log` 최신 로그 선정 수정**:
  - `sync_*.log` 파일 패턴 매칭 및 `mtime` 수정 시각 기준 정렬로 정확한 최신 로그 탐색.
- **스크래퍼 파싱 예외 세분화 및 Fault Isolation**:
  - `NewneekScraper` 및 `CssSelectorScraper`에서 DOM/JSON 변경 시 개별 기사 단위 예외 포획 및 로그 기록 후 계속 진행.

### 3단계: 구조 개선 및 테스트 보강
- **안정성 및 경계 케이스 단위 테스트 추가**:
  - 파일명 sanitizing, OPDS 경로 대소문자 방어, Dashboard 로그 선택, 백업 flush 기능에 대한 pytest 작성.
- **문서 동기화**:
  - `CLAUDE.md` 내 이미 구현 완료된 항목들의 로드맵 설명 업데이트 및 정합성 유지.

---

## 6. Test Recommendations

추가 및 보강을 권장하는 구체적인 테스트 케이스 목록입니다.

1. **`tests/test_uploader_sanitize.py`**:
   - 한글 사이트명(예: `네이버뉴스_2026-07-31.epub`), 특수문자가 포함된 파일명이 식별력과 고유성을 잃지 않고 sanitizing 되는지 검증하는 단위 테스트.
2. **`tests/test_opds_path_case.py`**:
   - Windows 환경 드라이브 문자 대소문자 불일치(예: `C:\output` 대 `c:\output`) 상황을 가상화하여 `_serve_file()`이 403 오류를 반환하지 않고 정상 동작하는지 검증.
3. **`tests/test_service_backup_flush.py`**:
   - `schedule_backup_push` 호출 후 디바운스 시간이 지나기 전에 `flush_backup_push()`를 부를 때 유실 없이 백업 파일이 쓰이는지 검증.
4. **`tests/test_web_dashboard_log_selection.py`**:
   - `logs/` 디렉터리에 다양한 이름의 파일들이 혼재할 때, `DashboardHandler`가 정확히 가장 최근 수정된 `sync_*.log` 파일을 선택하는지 검증.
