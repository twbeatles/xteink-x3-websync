# Project Audit

> **감사 일자**: 2026-07-13  
> **최종 갱신**: 2026-07-13 (§3~§5 권장 수정 **구현 완료** 반영)  
> **감사 범위**: 기능 구현 관점 (예외 처리·입력 검증·상태/데이터 흐름·동시성·경로/인코딩·보안·테스트·문서 정합성)  
> **분석 도구**: `README.md`, `CLAUDE.md`, CodeGraph MCP, `pytest`  
> **테스트 결과**: `python -m pytest tests/ -q` → **63 passed**

---

## 1. Executive Summary

Xteink X3 WebSync Manager는 **수집 → (선택) 번역/요약 → EPUB 빌드 → 다중 기기 무선 전송** 파이프라인을 `websync/` 패키지로 분리한 데스크톱 도구입니다.

| 항목 | 평가 |
|------|------|
| **전체 위험도** | **Low–Medium** (2026-07-13 수정 후) |
| **아키텍처·모듈 분리** | 양호 |
| **§3 High-Risk 이슈** | ✅ 권장 수정 전면 반영 (부록 C) |
| **잔여 리스크** | LAN HTTP 평문(의도·문서화), GUI/Translator E2E 테스트 공백, EXE 선택 기능 제외(문서화) |
| **테스트** | **63건** — paths, process_lock, epub, pipeline, db, opds, uploader 등 |

**한 줄 요약**: 2026-07-13 감사에서 지적한 Critical/High 항목(frozen 경로, 프로세스 락, save_config, IP 키, 부분 재전송 등)을 코드에 반영했고, 문서·테스트를 동기화했습니다.

---

## 2. Project Understanding

### 2.1 목적

Xteink X3(CrossPoint) e-ink 리더기에 웹·RSS·블로그·YouTube 등 콘텐츠와 Calibre 도서를 EPUB 등으로 빌드해 Wi-Fi HTTP 업로드하는 GUI/CLI 도구. SQLite `sync_history.db`로 URL·**기기 IP** 단위 증분 동기화.

### 2.2 모듈 구성

| 모듈 | 역할 |
|------|------|
| `x3_websync.py` | 진입점 — GUI 단일 인스턴스(Windows mutex + 락 파일), `--sync` |
| `websync/core/paths.py` | `PROJECT_ROOT` — 개발: 패키지 상위 / **frozen: exe 디렉터리** |
| `websync/core/process_lock.py` | **크로스 프로세스** 파이프라인 파일 락 |
| `websync/config/manager.py` | config CRUD, 원자 저장, `ConfigSaveError` |
| `websync/pipeline/service.py` | 오케스트레이터 — thread + process 락, 미전송 기기만 업로드 |
| `websync/upload/uploader.py` | 업로드 결과 키 = **IP**, `only_ips` 필터 |
| `websync/db/history.py` | 기기별 이력, 삭제/조회 fail-closed |
| `websync/scrapers/*` | 7종 + CSS `fetch_detail_page`, skip 통계 |
| `websync/servers/*` | OPDS URL 인코딩, 웹 세션 만료·`compare_digest` |
| `websync/gui/app.py` | Tkinter UI, `_safe_save_config` |

### 2.3 주요 실행 흐름

```
main()
  ├── [GUI] acquire_instance_lock (mutex+file) → SyncAppGui
  └── [--sync] SyncService.run_sync_pipeline()
                 ├── _pipeline_lock (thread)
                 ├── ProcessFileLock (cross-process)
                 └── _run_sync_pipeline_locked
                      → fetch → needs_sync → build
                      → upload_to_targets(only_ips=pending)
                      → mark_synced(device_ip=ip)
```

---

## 3. High-Risk Issues (감사 시점 → 조치 상태)

### 3.1 PyInstaller frozen `PROJECT_ROOT` — ✅ 수정됨

* **위치**: `websync/core/paths.py` — `_detect_project_root()`
* **조치**: `sys.frozen` 시 `dirname(sys.executable)`. README에 EXE 데이터 경로 명시.
* **우선순위(잔여)**: Low — EXE 스모크는 CI 미포함 **(추정)**

### 3.2 프로세스 간 파이프라인 동시 실행 — ✅ 수정됨

* **위치**: `websync/core/process_lock.py`, `SyncService.run_sync_pipeline`
* **조치**: thread lock + `ProcessFileLock` 비차단 획득. 다른 프로세스 점유 시 False 반환.

### 3.3 부분 재시도 시 성공 기기 재전송 — ✅ 수정됨

* **위치**: `service.py` — `pending_ips` + `upload_to_targets(..., only_ips=)`
* **조치**: 배치 내 미전송 기기만 업로드. 테스트 `test_pipeline_skips_already_synced_device_on_retry`.

### 3.4 `save_config` silent 실패 — ✅ 수정됨

* **위치**: `ConfigSaveError`, GUI `_safe_save_config`
* **조치**: 저장 실패 시 예외 전파 및 메시지 박스.

### 3.5 기기 이름 키 충돌 — ✅ 수정됨

* **위치**: `uploader.upload_to_targets` → `{ip: bool}`; GUI 이름/IP 중복 검사

### 3.6 웹/OPDS LAN 보안 — ✅ 부분 개선

* **조치**: `secrets.compare_digest`, 세션 7일 만료·`Max-Age`, OPDS 헤더 우선. TLS는 미도입(의도적, README 경고 유지).
* **잔여**: 비신뢰 LAN에서 HTTP 스니핑 가능 → 문서 고지.

### 3.7 EXE 선택 기능 제외 — ✅ 문서화

* **조치**: README 표로 Pillow/youtube/watchdog/googletrans 제외 명시.

### 3.8 Calibre UI 스레드 로드 — ✅ 수정됨

* **조치**: 워커에서 `list_books()` 후 `after`로 UI 갱신.

### 3.9 Windows GUI 인스턴스 락 — ✅ 강화

* **조치**: named mutex `Local\\XteinkX3WebSync_GUI_SingleInstance` + 락 파일.

### 3.10 OPDS 한글 파일명 — ✅ 수정됨

* **조치**: `quote`/`unquote`, RFC 5987 `filename*`.

### 3.11 이력 삭제 silent — ✅ 수정됨

* **조치**: `SyncHistoryDbError` + GUI 오류 처리.

### 3.12 스크래퍼 포스트 단위 silent — ✅ 개선

* **조치**: `last_fetch_stats`, 전량 실패 시 예외, 파이프라인 스킵 건수 로그.

---

## 4. Potential Functional Gaps (잔여)

| 구분 | 내용 |
|------|------|
| **LAN HTTP** | 웹 대시보드·OPDS LAN은 평문 — reverse proxy TLS 권장 |
| **GUI/Translator 테스트** | 단위 테스트 없음 (수동·E2E 공백) |
| **CSS 상세 페이지** | `fetch_detail_page` 옵션 추가됨 — 사이트별 셀렉터 튜닝 필요 |
| **스케줄 desync** | `config.schedule.enabled`와 OS 작업 등록 수동 불일치 가능 |
| **Watch on_moved** | 이동으로 들어온 파일 미감지 **(추정)** |

---

## 5. Recommended Fix Plan — 완료 현황

### 1단계 ✅
1. frozen `PROJECT_ROOT`  
2. 크로스 프로세스 파이프라인 락  
3. `save_config` 실패 전파  
4. 업로드/이력 IP 키 통일  

### 2단계 ✅
5. 미전송 기기만 재업로드  
6. Calibre 워커 스레드  
7. OPDS 파일명 인코딩  
8. history fail-closed  
9. 스크래퍼 skip 통계·전량 실패 예외  
10. README EXE 제외 기능  

### 3단계 ✅ (문서·보안·테스트)
11. Windows GUI mutex  
12. compare_digest / 세션 만료  
13. CLAUDE/README/AUDIT 동기화  
14. paths·process_lock·epub 테스트  
15. CSS `fetch_detail_page`  

---

## 6. Test Recommendations

| 상태 | 내용 |
|------|------|
| ✅ | frozen 경로 단위 테스트 (`test_paths.py`) |
| ✅ | process lock (`test_process_lock.py`) |
| ✅ | only_ips / partial re-upload (`test_service.py`, `test_uploader.py`) |
| ✅ | ConfigSaveError (`test_config_manager.py`) |
| ✅ | EpubBuilder (`test_epub_builder.py`) |
| ✅ | OPDS 유니코드 다운로드 (`test_opds.py`) |
| 잔여 | GUI smoke, Translator, frozen EXE 통합 스모크, Calibre mock |

```bash
python -m pytest tests/ -q
# 2026-07-13: 63 passed
```

---

## 부록 A. 검증 명령

```bash
python -m pytest tests/ -q
```

## 부록 B. 의도적 설계

- OPDS localhost 무인증 편의  
- AI/번역 옵트인 + config 평문 키  
- EXE 경량화를 위한 optional 패키지 excludes  

## 부록 C. 2026-07-13 구현 체크리스트

| 이슈 | 상태 |
|------|------|
| frozen PROJECT_ROOT | ✅ |
| ProcessFileLock | ✅ |
| ConfigSaveError / GUI | ✅ |
| upload IP keys + only_ips | ✅ |
| pending device re-upload | ✅ |
| Calibre worker | ✅ |
| OPDS quote + filename* | ✅ |
| DB delete fail-closed | ✅ |
| scraper stats / all-fail raise | ✅ |
| CSS fetch_detail_page | ✅ |
| Windows GUI mutex | ✅ |
| web session expiry + compare_digest | ✅ |
| docs + tests (63) | ✅ |
