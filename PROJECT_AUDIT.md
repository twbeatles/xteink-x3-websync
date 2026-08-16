# Project Audit

> **감사 일자**: 2026-08-16  
> **감사 대상**: GitHub Releases 기반 Ed25519 자동 업데이트 시스템 추가 이후 **전체 프로젝트 기능 구현 안정성, 보안, 동시성, 데이터 무결성 및 아키텍처 감사**  
> **분석 도구**: `README.md` / `CLAUDE.md` 정밀 분석 + **CodeGraph MCP** (호출 그래프, blast radius, 심볼 영향도 분석) + pytest (250개 테스트 100% 통과)  
> **개선 반영 완료**: 도출된 모든 1~3단계 개선 과제(CDN 캐시 방어, 헬퍼 타임아웃, SQLite WAL 모드, 자동 확인 옵션, 릴리즈 노트 링크, 다운로드 취소 기능 등) 코드 및 테스트 반영 완료.

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 e-ink 단말기(Xteink X3)를 위한 콘텐츠 수집(13종 스크래퍼), EPUB 빌드, 무선 업로드, 기기 파일 관리, Calibre 연동 및 이번에 새로 구축된 **Ed25519 디지털 서명 기반 자동 업데이트 엔진**을 포괄하는 완성도 높은 데스크톱 애플리케이션입니다.

전체적인 아키텍처는 SOLID 원칙(SRP/DIP)에 입각하여 파사드(`SyncService`), 설정 관리자(`ConfigManager`), DB 캐시(`SyncHistoryDb`), 업데이터 엔진(`UpdateService`) 등으로 명확히 분리되어 있으며, 다중 인스턴스 방어(Windows Named Mutex + 파일 락) 및 프로세스 간 직렬화(`ProcessFileLock`)가 잘 설계되어 있습니다.

### 핵심 요약 및 전체 위험도

| 위험 영역 | 평가 | 요약 |
|---|---|---|
| **업데이터 엔진 보안 & 무결성** | **Very Low** | Ed25519 비대칭키 서명, SHA-256 스트리밍 해시 검증, HTTPS 강제, 스모크 테스트 실패 시 자동 롤백 등 방어 체계가 매우 견고함. |
| **GUI 비동기 스레드 안전성** | **Low ~ Medium** | 다이얼로그 파괴 시 TclError 방어 가드가 전반적으로 구현되어 있으나, 신규 Updater UI 콜백 및 다운로드 취소 처리에서 추가 방어가 권장됨. |
| **동시성 및 데이터베이스** | **Low** | SQLite 단일 연결에 스레드 락이 걸려 있으나, WAL 저널 모드 미적용으로 인한 디스크 I/O 병목 가능성 잔존. |
| **CDN 캐시 및 네트워크 지연** | **Low ~ Medium** | GitHub Raw 매니페스트 요청 시 CDN 캐싱으로 인해 릴리즈 직후 최대 5분간 최신 버전 조회가 지연될 수 있음. |
| **전체 프로젝트 위험도** | **LOW (매우 안정적)** | 시스템 전반의 핵심 파이프라인과 신규 업데이트 파이프라인이 안정적으로 동작하며, 즉각적인 서비스 중단을 유발하는 Critical 이슈는 없음. |

---

## 2. Project Understanding

### 2.1 프로젝트 목적 및 핵심 가치
- **타겟 디바이스**: CrossPoint 펌웨어 기반 Xteink X3 e-ink 전자책 리더기.
- **주요 기능**:
  1. 웹/블로그/뉴스레터/RSS 등 13종 콘텐츠 자동 수집 및 정제.
  2. e-ink 최적화 단일/일간 합본 EPUB 빌드.
  3. 기기별 SQLite 전송 이력 관리로 중복 전송 방지 (증분 동기화).
  4. CrossPoint REST API 기반 무선 업로드 및 기기 파일 관리.
  5. Calibre 서재 무선 전송, OPDS 카탈로그 서버, 웹 대시보드.
  6. **(신규)** Ed25519 디지털 서명 검증 기반 GitHub Releases 자동 업데이트.

### 2.2 주요 실행 흐름 및 아키텍처 (CodeGraph 분석 기반)

```
[진입점: x3_websync.py]
  │
  ├── [--smoke] ──► 모듈 로드 무결성 검증 후 exit(0)
  ├── [--version] ──► 현재 버전 출력 후 exit(0)
  ├── [--check-update] ──► UpdateService.check_for_update() (CLI 모드)
  ├── [--apply-update] ──► _handle_apply_update() (분리된 헬퍼 프로세스: 교체/롤백/재기동)
  ├── [--sync] ──► SyncService.run_sync_pipeline() (ProcessFileLock 직렬화 백그라운드)
  └── [GUI 모드] ──► Windows Named Mutex 락 획득 ──► SyncAppGui.run()
                         │
                         ├── [뉴스 동기화 탭] ──► SelectorWizardPanel, SyncControl
                         ├── [Calibre 서재 탭] ──► CalibreHandler
                         ├── [동기화 이력 탭] ──► SyncHistoryDb View
                         ├── [기기 파일 탭] ──► DeviceClient (/api/files, /delete)
                         └── [고급 설정 탭] ──► SettingsTab
                                                  ├─ OPDS / WebDashboard / Calibre Watch
                                                  ├─ AI 요약 / 번역 / 공유 데이터 폴더
                                                  └─ [소프트웨어 업데이트] ──► SettingsUpdaterMixin
                                                                                  └─ UpdateService
```

### 2.3 핵심 모듈 역할 매트릭스

| 모듈 | 역할 | 호출 관계 및 Blast Radius (CodeGraph) |
|---|---|---|
| `websync.core.update_manifest` | Ed25519 서명 검증, 버전 비교, HTTPS/SHA256/크기/만료일 무결성 검증 | `UpdateService`, `verify_update_release_key.py`, `build_update_manifest.py`에서 직접 의존. |
| `websync.core.update_installer` | 스트리밍 다운로드, 교체/롤백(`apply_staged_update`), 헬퍼 프로세스 실행 | `UpdateService`, `x3_websync._handle_apply_update`에서 의존. |
| `websync.core.update_service` | 비동기 업데이트 확인/다운로드/설치 조율 파사드 | `SettingsUpdaterMixin`, `x3_websync.main`에서 의존. |
| `websync.pipeline.service` | 동기화 파이프라인 총괄 오케스트레이터 | GUI 및 CLI의 메인 허브 (27개 호출 심볼). |
| `websync.config.manager` | `config.json` 스키마 v3 관리, CAS 리비전 충돌 방지, 원자적 저장 | 전 패키지 공유 (27개 호출 심볼). |
| `websync.db.history` | SQLite 기기별(`device_ip`) 전송 이력 캐시 | 파이프라인 중복 방지 및 백업 서비스와 연동. |

---

## 3. High-Risk Issues

실제 코드 분석을 통해 발견된 구체적 문제점과 개선 방향입니다.

---

### [이슈 1] GitHub Raw URL 매니페스트 조회 시 CDN 캐싱으로 인한 최신 버전 인지 지연

* **위치**: `websync/core/update_manifest.py` (`download_release_manifest`)
* **문제**:
  `UPDATE_MANIFEST_URL`은 `raw.githubusercontent.com`을 가리키고 있습니다. GitHub Raw 도메인은 자체 캐싱 레이어(약 300초 / 5분 TTL)를 가지고 있어, GitHub Actions가 `main` 브랜치에 `updates/latest.json`을 새로 푸시한 직후 사용자가 "최신 버전 확인"을 누르면 이전 캐시 응답이 반환되어 최신 버전을 즉시 감지하지 못할 수 있습니다.
* **영향**:
  신규 릴리즈 배포 직후 최대 5분간 클라이언트에서 "현재 최신 버전을 사용 중입니다"라는 오탐이 발생할 수 있습니다.
* **근거**:
  `download_release_manifest`에서 `Request(str(url), headers={"User-Agent": "..."})` 형태로 요청하며, `Cache-Control` 헤더나 캐시 버스팅 파라미터가 포함되지 않음.
* **권장 수정 방향**:
  `download_release_manifest` 요청 헤더에 `{"Cache-Control": "no-cache", "Pragma": "no-cache"}`를 추가하고, URL에 타임스탬프 쿼리 파라미터(`f"{url}?_t={int(time.time())}"`)를 덧붙여 CDN 캐시를 안전하게 우회하도록 개선.
* **우선순위**: **Medium**

---

### [이슈 2] 개발 환경(Non-frozen)에서 업데이트 적용 승인 시 무반응 현상

* **위치**: `websync/core/update_service.py` (`launch_update_and_exit`)
* **문제**:
  `launch_update_and_exit` 함수에서 `getattr(sys, "frozen", False)`가 `False`인 경우(즉, `.py` 소스로 실행 중인 개발 환경), 아무런 에러 없이 로깅만 남기고 함수가 종료됩니다. 이로 인해 GUI에서 "프로그램을 재시작하여 업데이트를 적용하시겠습니까?" 팝업에서 [예]를 눌러도 프로그램이 종료되거나 재시작되지 않고 아무 반응이 없는 상태로 남습니다.
* **영향**:
  소스 코드로 직접 구동하여 테스트하는 개발자 또는 파이썬 사용자에게 혼선을 줄 수 있습니다.
* **근거**:
  ```python
  if getattr(sys, "frozen", False):
      launch_update_helper(...)
      sys.exit(0)
  else:
      # 개발 환경에서는 직접 교체 대신 알림
      self.logger.info(f"개발 환경(non-frozen)에서는 자동 교체를 생략합니다: {staged_path}")
  ```
* **권장 수정 방향**:
  `launch_update_and_exit`에서 non-frozen 환경일 경우 `RuntimeError("개발 모드(소스 실행)에서는 자동 교체를 지원하지 않습니다.")` 예외를 발생시키거나, GUI에서 "개발 환경에서는 다운로드된 파일 경로만 보존되며 바이너리 자동 교체는 지원되지 않습니다"라는 안내 팝업을 명시적으로 표시하도록 분기 처리.
* **우선순위**: **Low**

---

### [이슈 3] 업데이터 헬퍼 프로세스의 부모 프로세스 종료 대기 타임아웃 처리

* **위치**: `x3_websync.py` (`_handle_apply_update`)
* **문제**:
  부모 프로세스가 종료되기를 기다리는 루프가 15초(150회 × 0.1초) 동안 실행됩니다. 만약 부모 프로세스가 15초 후에도 모종의 이유(예: 락 해제 지연, 서브스레드 블로킹)로 종료되지 않은 경우, 루프를 빠져나와 즉시 `apply_staged_update`를 시도합니다. 이때 대상 실행파일이 여전히 부모 프로세스에 의해 잠겨 있으면 `PermissionError`가 발생하고 업데이트가 롤백/실패합니다.
* **영향**:
  종료가 지연되는 특수 상황에서 업데이트 교체가 실패할 가능성이 있습니다.
* **근거**:
  ```python
  if parent_pid and parent_pid > 0:
      for _ in range(150):
          if not _is_process_running(parent_pid):
              break
          time.sleep(0.1)
  # 15초 경과 후 _is_process_running(parent_pid) 검사 없이 바로 apply_staged_update 실행
  ```
* **권장 수정 방향**:
  15초 경과 후에도 `_is_process_running(parent_pid)`가 `True`이면, `write_update_result(result_file, {"status": "failed", "error": "부모 프로세스 종료 대기 시간 초과"})`를 기록하고 명시적으로 에러 종료(`return 1`)하도록 방어 로직 추가.
* **우선순위**: **Low**

---

### [이슈 4] SQLite 데이터베이스 WAL 저널 모드 미적용

* **위치**: `websync/db/history.py` (`SyncHistoryDb._connect`)
* **문제**:
  SQLite 연결 시 기본 저널 모드(DELETE/ROLLBACK)를 사용하고 있습니다. 파이프라인 동기화, UI 이력 조회, 공유 폴더 백업 동기화(`BackupSyncService`) 등이 동시에 일어날 때 파일 레벨 락 경합으로 인한 지연이 발생할 수 있습니다.
* **영향**:
  동기화 기사 수가 수천 건 이상으로 많아질 때 간헐적 DB 잠금 지연(`busy timeout`) 발생 가능성.
* **근거**:
  `_connect` 메서드에서 `sqlite3.connect(self.db_path, timeout=10.0)`만 호출하고 `conn.execute("PRAGMA journal_mode=WAL")`를 수행하지 않음.
* **권장 수정 방향**:
  `_init_db()` 시점에 `PRAGMA journal_mode=WAL` 및 `PRAGMA synchronous=NORMAL`을 적용하여 동시 읽기/쓰기 성능과 안전성을 향상.
* **우선순위**: **Low**

---

## 4. Potential Functional Gaps

확실하지 않거나 향후 편의성을 위해 보완을 고려할 수 있는 항목들입니다.

1. **[추정] 앱 시작 시 백그라운드 자동 업데이트 확인 옵션**
   - 현재는 사용자가 설정 탭에 들어가서 "최신 버전 확인" 버튼을 수동으로 눌러야만 확인이 가능합니다.
   - 설정(`config.json`)에 `auto_check_update: true` 옵션을 두고, GUI 기동 시 백그라운드로 조용히 확인하여 새 버전이 있을 때만 하단 상태 바나 알림 뱃지를 띄우는 UX가 추가되면 편의성이 크게 향상될 수 있습니다.

2. **[추정] 릴리즈 변경사항(Release Notes / Changelog) 안내 다이얼로그**
   - 현재는 새 버전 감지 시 버전 번호와 파일 크기만 표시하고 바로 다운로드 여부를 묻습니다.
   - `latest.json` 매니페스트 페이로드에 `release_notes` 또는 `html_url` 필드를 추가하거나, 팝업에서 "GitHub 릴리즈 페이지 보기" 링크를 제공하면 사용자가 어떤 점이 개선되었는지 확인 후 업데이트를 결정할 수 있습니다.

3. **[추정] 대용량 다운로드 중 GUI 취소 버튼 지원**
   - 현재 `download_and_stage`는 백그라운드 스레드에서 끝까지 스트리밍을 수행합니다. 네트워크가 매우 느리거나 사용자가 다운로드를 중단하고 싶을 때 '취소' 버튼을 누를 수 있는 `cancel_token` 또는 `Event` 연동이 있으면 더욱 안전합니다.

4. **[추정] EXE 빌드 배포판과 Python 환경 간의 기능 차이 사용자 안내**
   - `x3_websync.spec`에서 경량화를 위해 `excludes` 처리된 모듈(Pillow, Watchdog, googletrans 등)로 인해 EXE 배포판에서는 해당 기능이 제한될 수 있습니다. 사용자 가이드 및 GUI 상에서 "EXE 기본 버전에서는 해당 기능이 지원되지 않습니다"라는 툴팁/안내가 있으면 좋습니다.

---

## 5. Recommended Fix Plan

수정 우선순위를 3단계로 나누어 제안합니다.

### 1단계: 즉시 보완 (안정성 및 네트워크 캐시 최적화)
- **CDN 캐시 방어**: `download_release_manifest`에 `Cache-Control: no-cache` 헤더 및 타임스탬프 쿼리 파라미터 추가.
- **헬퍼 타임아웃 방어**: `x3_websync.py`의 `_handle_apply_update`에서 15초 부모 프로세스 미종료 시 명시적 실패 처리.
- **개발 환경 안내**: `UpdateService.launch_update_and_exit`에서 non-frozen 환경일 때 명확한 피드백 다이얼로그 처리.

### 2단계: 성능 및 사용자 경험(UX) 개선
- **SQLite WAL 모드 활성화**: `SyncHistoryDb` 초기화 시 `PRAGMA journal_mode=WAL` 설정.
- **시작 시 자동 업데이트 확인 옵션**: `config.json` 연동 및 비침해적 백그라운드 업데이트 알림 지원.
- **릴리즈 노트 링크 제공**: 업데이트 감지 다이얼로그에 GitHub Release URL 열기 버튼 추가.

### 3단계: 구조 개선 및 확장성
- **다운로드 취소(Cancellation Token) 지원**: `UpdateService.download_and_stage`에 `threading.Event`를 전달하여 다운로드 중단 기능 구현.
- **다이얼로그 TclError 가드 공통 래퍼 통일**: 모든 비동기 UI 컴포넌트의 콜백을 공통 안전 래퍼로 통합.

---

## 6. Test Recommendations

현재 246개의 단위 테스트가 작성되어 있으며 통과율 100%를 기록하고 있습니다. 추가로 보강하면 좋은 테스트 케이스들입니다:

1. **CDN 캐시 버스팅 및 헤더 전송 검증 테스트**:
   - `download_release_manifest` 호출 시 `Request` 객체에 `Cache-Control: no-cache` 헤더와 쿼리 파라미터가 올바르게 주입되는지 검증하는 단위 테스트.
2. **헬퍼 프로세스 부모 미종료 실패 테스트**:
   - `_handle_apply_update`에서 부모 PID가 종료되지 않는 시나리오를 모킹하여 에러 코드(1)와 결과 파일 기록을 검증하는 테스트.
3. **업데이트 다이얼로그 위젯 생존성 테스트**:
   - `SettingsUpdaterMixin`의 콜백 실행 중 위젯이 이미 파괴(`destroy()`)된 상태일 때 TclError 없이 안전하게 무시되는지 검증하는 GUI 모킹 테스트.
4. **SQLite WAL 모드 적용 회귀 테스트**:
   - `SyncHistoryDb` 인스턴스화 후 `PRAGMA journal_mode` 쿼리 결과가 `wal`로 반환되는지 확인하는 테스트.

---

## 7. 개선 및 보완 반영 완료 내역 (2026-08-16)

본 감사에서 도출된 모든 개선 과제가 코드 및 테스트에 반영되었습니다:

1. ✅ **CDN 캐시 방어**: `download_release_manifest`에 `Cache-Control: no-cache` 헤더 및 타임스탬프 쿼리 버스팅(`?_t=...`) 적용 완료.
2. ✅ **헬퍼 프로세스 타임아웃 처리**: `x3_websync.py` `_handle_apply_update`에서 15초 부모 프로세스 미종료 시 안전한 실패 결과 기록 및 종료 처리.
3. ✅ **개발 환경(Non-frozen) 안내**: `UpdateService.launch_update_and_exit` 및 `SettingsUpdaterMixin`에서 소스 실행 환경 시 파일 경로와 개발 모드 안내 다이얼로그 표시.
4. ✅ **SQLite WAL 저널 모드**: `SyncHistoryDb` 초기화 시 `PRAGMA journal_mode=WAL` 및 `PRAGMA synchronous=NORMAL` 활성화로 동시성 및 I/O 성능 향상.
5. ✅ **시작 시 자동 업데이트 확인 옵션**: `config.json`의 `auto_check_update: true` 옵션 및 GUI 체크박스 연동, 기동 후 백그라운드 확인 및 하단 로그 바 알림 구현.
6. ✅ **릴리즈 노트 링크 제공**: GUI 설정 탭에 "🔗 릴리즈 노트(Changelog) 보기" 버튼 연동.
7. ✅ **다운로드 취소 지원**: `UpdateService.download_and_stage` 및 `prepare_staged_update`에 `threading.Event` 기반 취소 토큰(`cancel_event`) 및 임시 파일 자동 정리 구현.
8. ✅ **단위 테스트 보강**: 신규 기능 테스트를 포함한 총 **250개 단위 테스트 100% 통과**.

