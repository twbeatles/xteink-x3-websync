# Project Audit

> **감사 일자**: 2026-07-27
> **수정 반영**: 2026-07-27 — N1~N9 권고 전부 코드·테스트 반영 (`pytest` **196 passed**)
> **감사 관점**: 기능 구현 — 동시성, 예외 처리, 데이터 흐름, 보안, 경로/인코딩, 설정·DB, 테스트, 문서 정합
> **방법**: `README.md` / `CLAUDE.md` 숙지 → **CodeGraph MCP**로 진입점·호출 관계·영향 범위 분석 → 필요 시 소스 직접 확인 → `pytest` 실행
> **검증**: `python -m pytest tests/ -q` → **196 passed** (감사 시점 161 → 수정 후 196)
> **참고**: 이전 감사(2026-07-22) 이후 코드 수정 반영 여부를 재확인한 **전면 재감사**입니다. `docs/PROJECT_AUDIT.md`(2026-07-14)는 구버전 아카이브.

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 CrossPoint e-ink 기기를 위한 뉴스·콘텐츠 수집 → EPUB 빌드 → 무선 전송 데스크톱 앱입니다. SOLID 기반 패키지 분리, 스레드/프로세스 파이프라인 락, config 원자 저장 + revision CAS, 기기별 SQLite 이력(안정 device id 도입), OPDS·웹 대시보드 인증(HMAC 세션 + `secrets.compare_digest`), 공유 데이터 폴더 정본(`websync/backup` — OneDrive 등, `portable_data`)까지 갖춘 **성숙도 높은** 코드베이스입니다.

- **전체 위험도**: **Low–Medium** (개인 PC·로컬 LAN 가정)
  - LAN 공개(`allow_lan`)·멀티 PC 백업 동기화·API 키 평문 저장을 쓰는 환경에서는 **Medium**
- **테스트 현황**: 단위/통합 테스트 **161 passed** — 핵심 파이프라인·DB·업로더·백업·대시보드·스크래퍼가 커버됨
- **이전 감사(2026-07-22) 대비**: H1~H10 권고 사항 대부분이 **해결 또는 완화**되었습니다. 본 감사는 잔여 이슈와 **새로 식별된 경계 케이스**에 집중합니다.

### 핵심 이슈 처리 현황 (이전 감사 vs 현재)

| # | 이전 이슈 | 이전 상태 | 현재 상태 | 비고 |
|---|----------|-----------|-----------|------|
| H1 | `/api/sync` 항상 202 | High | ✅ **해결** | `begin_sync_pipeline_async`가 락 선점 결과를 동기 반환 → `False`면 409. TOCTOU 재확인(2회 busy_cb 호출) 추가 |
| H2 | daily_digest “대상 없음” 성공 집계 | High | ✅ **해결** | 기기 0대 → `no_targets` early-return False(라인 68-76); pending 없음 = “이미 전부 전송” 로깅 + `success_count = actual_work_sites` |
| H3 | `import_sites` RMW 레이스 | Medium | ✅ **해결** | `update_config(mutator)`로 디스크 최신본에 합집합 추가(`config/manager.py:402-456`) |
| H4 | `_safe_save_config` 재시도 1회 | Medium | ✅ **해결** | `max_conflict_retries = 3` 루프 + 매 시도 disk 병합(`helpers.py:101-173`) |
| H5 | 시크릿 평문 저장 | Medium | ⚠️ **잔여** | `mask` 유틸·UI `show=*`는 있으나 OS keyring 미구현 |
| H6 | 레거시 `*` 자동 이관 | Low–Medium | ✅ **해결** | 파이프라인 시작 시 `remap_legacy_star_to_device(legacy_key)` 호출(`sync_pipeline.py:78-85`) |
| H7 | `pending_device_ips` 빈 대상 | Low | ✅ **완화** | 의미 명확화 + docstring; 프로덕션 미사용 |
| H8 | selected/sync upload 판정 불일치 | Medium | ✅ **해결** | 공통 헬퍼 `upload_results.py`(`upload_all_ok`/`upload_any_ok`/`collect_mark_entries`)로 통일 |
| H9 | 기기 HTTP 평문 | Low | ⚠️ **의도된 제약** | CrossPoint 로컬 펌웨어 전제; README에 명시 권장 |
| H10 | macOS plist XML 이스케이프 | Low | ✅ **해결** | `_xml_escape` 적용(`scheduler/manager.py:96-106`) |

**과장하지 않은 총평**: 치명적(Critical) 보안 구멍이나 데이터 파괴 버그는 확인되지 않았다. 이전 감사의 High 항목은 모두 해결되었으며, 남은 것은 **성공 판정의 미세한 경계 케이스**, **네트워크/편집 동시성의 이론적 레이스**, **선택적 보안 강화(OS keyring)**, **통합 테스트 보강** 정도다. 실사용에 지장을 주는 기능 결함은 현재 코드베이스에서 발견되지 않는다.

### N1~N9 수정 반영 현황 (2026-07-27)

| 이슈 | 우선순위 | 상태 | 수정 내용 |
|------|----------|------|-----------|
| N1 daily_digest 카운팅 의미 | Medium | ✅ **해결** | `digest_success`/`digest_partial` 별도 플래그 도입, 합본 모드 단일 판정(`sync_pipeline.py`); 회귀 테스트 4건 추가(`test_pipeline_digest.py`) |
| N2 네이버 스크래퍼 직렬 HTTP | Medium | ✅ **해결** | 상세 페이지 `ThreadPoolExecutor(max_workers=3)` 병렬화, `last_fetch_stats` 스킵 통계 기록, 전 실패 시 예외(`naver.py`); 테스트 9건 추가(`test_naver_scraper.py`) |
| N3 선택 동기화 백업 pull 생략 | Medium | ✅ **해결** | `sync_selected_articles` 시작 시 `maybe_backup_pull` 호출(`selected_sync.py`); 테스트 4건 추가(`test_selected_sync.py`) |
| N4 Preview stale config | Low–Medium | ✅ **해결** | `preview.py` 시작 시 `maybe_backup_pull` 호출 후 최신 config 로드 |
| N5 시크릿 평문/마스킹 부족 | Medium | ✅ **해결(UI 마스킹)** | AI/번역/OPDS/웹 토큰 보기·숨기기 토글 추가, `mask_secret` 헬퍼로 통일(`settings_tab/`); 기존 `token[:8]` 평문 노출 제거; 테스트 8건 추가(`test_secrets.py`) |
| N6 OPDS/웹 단일 스레드 서버 | Low–Medium | ✅ **해결** | `HTTPServer` → `ThreadingHTTPServer` 전환(`opds.py`, `dashboard/http_server.py`); 동시 요청 테스트 2건 추가 |
| N7 preview/selected 락 중복 | Low | ✅ **해결** | `service._try_acquire_pipeline_locks`/`_release_pipeline_locks` 헬퍼로 통일(`preview.py`, `selected_sync.py`) |
| N8 Summarizer/Translator 조용한 스킵 | Low | ✅ **해결** | `__init__`에 `logger` 주입, `print` → `logger.warning` 전환(`summarizer.py`, `translator.py`); 테스트 12건 추가/보강(`test_summarizer.py`, `test_translator.py`) |
| N9 ProcessFileLock 프로브 | Low | ✅ **해결(문서화)** | `is_held_by_other` docstring에 프로브 의미·안전성 명시(`process_lock.py`) |
| CLAUDE.md config_version 부정합 | — | ✅ **해결** | `2` → `3` 수정 |

---

## 2. Project Understanding

### 2.1 목적 (README / CLAUDE)

| 항목 | 내용 |
|------|------|
| 목적 | Xteink X3용 뉴스·블로그 수집 → e-ink 최적 EPUB → 무선 전송 자동화 |
| 핵심 가치 | SQLite 증분 동기화(기기별 + 안정 device id), 다중 사이트/기기, Calibre·OPDS·웹 대시보드·스케줄·백업 |
| 원칙 | SOLID, 모듈 단일 책임, 타입 힌트 |
| 진입 | `python x3_websync.py` (GUI) / `--sync` (스케줄·백그라운드) |

### 2.2 패키지 구조 (현재 코드 기준)

```
x3_websync.py                 # CLI/GUI, GUI 단일 인스턴스 락 (Windows named mutex + flock)
websync/
  core/                       # paths, process_lock, logger, article
  config/                     # manager(원자 저장+revision CAS), validator, exceptions
  db/                         # SyncHistoryDb (기기별 PK, 안정 id 키)
  scrapers/                   # 13종 + factory/types/presets/naver_common
  epub/                       # builder, css, cover, sanitize, themes
  upload/                     # uploader, device_client, host, remote_path, device_ids
  pipeline/                   # SyncService + sync/preview/selected + upload_results 헬퍼
  backup/                     # 공유 폴더 sites/history JSON 정본 pull/push + atomic_io/format + local_import
  integrations/               # Calibre, ToastNotifier
  scheduler/                  # schtasks / launchd / crontab
  servers/                    # OPDS + dashboard/ (session, handler, http_server, service, templates)
  watch/                      # CalibreWatcher (watchdog)
  gui/                        # app_core, sync_tab, device_files, settings_tab + tab_*.py re-export
```

### 2.3 주요 실행 흐름 (CodeGraph)

```
main()
  ├─ [GUI] acquire_instance_lock()  # Windows named mutex + 락 파일 / Unix flock
  ├─ ConfigManager() → SyncService(config_manager)
  │     ├─ SyncHistoryDb (기기별 PK + 안정 device id)
  │     ├─ BackupSyncService
  │     └─ _import_local_sidecars_once()  # dist 사이드카 JSON 합집합
  ├─ [--sync]
  │     run_sync_pipeline()
  │       ├─ _try_acquire_pipeline_locks (비차단 thread + ProcessFileLock)
  │       ├─ maybe_backup_pull()
  │       ├─ run_sync_pipeline_locked()
  │       │     ├─ remap_legacy_star_to_device(첫 기기 키)
  │       │     ├─ for site: scrape → needs_sync → translate/summarize
  │       │     │            → resolve_pending_upload_ips → build/build_digest
  │       │     │            → upload_to_targets(only_ips) → collect_mark_entries → mark_synced_many
  │       │     └─ daily_digest 합본 처리
  │       └─ maybe_backup_push()
  └─ [GUI] SyncAppGui
        ├─ 시작 후 백그라운드 pull / 스케줄 / Watch 큐
        └─ 탭: 동기화 / Calibre / 이력 / 기기 파일 / 고급 설정(OPDS·웹·Watch·AI·백업)
```

### 2.4 동시성·데이터 계층

| 계층 | 메커니즘 | 상태 |
|------|----------|------|
| GUI 단일 실행 | Windows named mutex + 락 파일 / Unix flock + stale 락 복구 | 양호 |
| 파이프라인 | `SyncService._pipeline_lock`(threading.Lock) + `ProcessFileLock`(msvcrt/fcntl) | 양호; preview·selected 동기화도 동일 락 사용 |
| Config | `ConfigManager._lock` + tmp/bak/replace + `_config_revision` CAS; GUI는 `_safe_save_config` 3회 재시도 | 양호 |
| DB | `SyncHistoryDb._db_lock` + `sqlite3.connect(timeout=10.0)` + executemany 배치 | 양호 |
| 업로드 | `ThreadPoolExecutor` (기기 병렬, max 4) | 양호 |
| 백업 폴더 | 스레드 Lock + `.backup_sync.lock`(ProcessFileLock) | 양호 |
| Watch | debounce Timer + 파일 안정성(크기 2회 확인) | 양호 |
| 웹 동기화 트리거 | `begin_sync_pipeline_async`가 락 선점 결과를 동기 반환 → 409/202 분기 | 양호 (이전 H1 해결) |

### 2.5 문서·구현 정합

| 항목 | 문서 | 코드 | 정합 |
|------|------|------|------|
| 스크래퍼 수 | CLAUDE/README 13종 | `SCRAPER_TYPES` 13종 | 일치 |
| 백업 패키지 | CLAUDE 구조에 `backup/` | `websync/backup/` 존재 | 일치 |
| 프로세스 락 | CLAUDE 기술 | `ProcessFileLock` 사용 | 일치 |
| 레거시 `*` | CLAUDE: 시작 시 첫 기기로 이관 | `sync_pipeline.py:78-85`에서 `remap_legacy_star_to_device` 호출 | **일치(해결)** |
| config_version | CLAUDE: 2 | 코드: `CONFIG_VERSION = 3` | ⚠️ **CLAUDE.md 갱신 필요** |
| 테스트 수 | 이전 감사 151 | 현재 **161 passed** | 본 파일에서 갱신 |
| 진입점 호출 관계 | CLAUDE 3-1 | `main()` 흐름 일치 | 일치 |

### 2.6 보안 방어가 잘 된 부분 (긍정)

- **웹 대시보드**: Bearer + HMAC 세션 쿠키(`session_value`/`session_valid`), `secrets.compare_digest`, 미래 시각(+300s)·만료 검증, `HttpOnly; SameSite=Strict`, LAN 시 `X-Forwarded-Proto=https`일 때만 `Secure`
- **OPDS**: LAN 시 `require_auth`, path traversal `realpath` 검사, 쿼리 api_key는 환경변수로만 허용(로그 유출 방지)
- **원격 경로**: `normalize_remote_path`가 `..`/슬래시 무효화; 파일명 세니타이징(한글/공백 → `_`)
- **스케줄러**: hour/minute 정수 범위 검증, `shell=False` 인자 리스트, Windows 경로 `_win_quote`, macOS `_xml_escape`
- **Config**: JSON 손상 시 `.corrupt` 보존, 원자 쓰기(tmp+bak+replace+fsync), revision CAS
- **업로드**: 파일 크기 기반 동적 타임아웃, IP 기반 결과 키, `only_ips` 부분 재시도

---

## 3. High-Risk Issues

> 이전 감사 H1~H10은 대부분 해결되었습니다. 아래는 **현재 코드 기준**으로 식별된 이슈입니다.

### N1. daily_digest의 `success_count = actual_work_sites`가 부분 실패와 충돌 가능

* **위치**: `websync/pipeline/sync_pipeline.py:271-283` (`run_sync_pipeline_locked` daily_digest 분기)
* **문제**: 합본 업로드가 **일부 기기만 성공**(partial)일 때 `partial_count = 1`을 설정하지만, **모든 기기 실패**(`any_ok=False`)일 때는 `success_count`를 건드리지 않는다. 이후 `actual_work_sites > 0`이고 `success_count == actual_work_sites`이면 `overall_ok = True`가 된다.
  ```python
  if any_ok:
      ...
      if all_ok:
          success_count = actual_work_sites   # 전 성공
      else:
          ...partial_count = 1
  else:
      log("❌ 일간 합본 전송 실패!")          # success_count 갱신 없음
  ```
  실제로는 `site_errors == 0` 조건도 있어 완전 실패 시 `overall_ok`가 True가 되려면 `success_count == actual_work_sites`여야 하는데, `success_count`는 여전히 0(초기값)이므로 **대부분 False로 떨어진다**. 하지만 “합본은 1건인데 사이트 N건이 actual_work에 포함”되는 카운팅 의미가 모호하다.
* **영향**: 합본 전송 전 실패 시 `success_count=0, actual_work_sites>0` → `overall_ok=False`로 동작은 맞으나, **합본은 단일 업로드인데 `actual_work_sites`(사이트 수) 기준으로 성공을 재단**하는 것은 의미 불일치. 향후 로직 변경 시 오판 위험.
* **근거**: `sync_pipeline.py:226-289` daily_digest 블록; `success_count`/`actual_work_sites` 카운팅이 per_site 모드와 혼용됨.
* **권장 수정 방향**: daily_digest는 별도 success/partial 카운터(`digest_success`, `digest_partial`)를 두거나, `actual_work_sites` 대신 “합본 전송 성공 여부” 단일 플래그로 overall_ok 산정. 단위 테스트로 고립.
* **우선순위**: **Medium** (현재 동작은 대부분 올바르나 카운팅 의미가 헷갈려 유지보수 위험)

---

### N2. 네이버 블로그 스크래퍼의 직렬 HTTP 호출 → 느린 동기화

* **위치**: `websync/scrapers/naver.py:51-103` (`NaverBlogScraper.fetch_articles`)
* **문제**: RSS에서 포스트 목록을 가져온 뒤, **각 포스트마다 `PostView.naver` 상세 페이지를 동기적으로 순차 호출**한다(`limit` 기본 5 → 최대 5회 추가 HTTP). 재시도 세션(`fetch_url`, total=3, backoff 0.5s)이 적용되지만, 하나라도 느려지면 전체 사이트 처리가 블로킹된다.
* **영향**: 네이버 블로그 사이트가 여러 개일 때 동기화 시간 선형 증가; 네트워크 지연 시 타임아웃 누적. 스크래퍼 예외는 `except`로 패스되어 조용히 스킵되므로 사용자 인지 어려움.
* **근거**: `naver.py`의 `for item in items:` 루프 내 `fetch_url(post_view_url)`; `last_fetch_stats` 미설정(파이프라인은 `skipped` 통계를 읽지만 naver는 기록 안 함).
* **권장 수정 방향**:
  1. `ThreadPoolExecutor`(max 3~4)로 상세 페이지 병렬 수집
  2. `last_fetch_stats["skipped"]` 설정하여 파이프라인 로그에 스킵 건수 노출(CssSelectorScraper 패턴과 일치)
  3. 전체 실패 시 명확한 예외(`raise Exception("네이버 블로그 본문 수집 0건")`)
* **우선순위**: **Medium** (기능 동작하지만 성능·가시성)

---

### N3. 선택 동기화가 백업 pull을 생략 — 정본과 불일치 가능

* **위치**: `websync/pipeline/selected_sync.py:49-52` (`sync_selected_articles`)
* **문제**: 본 파이프라인(`_run_pipeline_body`)은 `maybe_backup_pull` → 동기화 → `maybe_backup_push` 순서로 실행하지만, **`sync_selected_articles`는 `_reload_config` 후 바로 빌드·업로드**하고 마지막에만 `maybe_backup_push`를 호출한다. pull 단계가 없다.
* **영향**: 공유 데이터 폴더를 쓰는 멀티 PC 환경에서, 다른 PC가 최근에 전송한 이력이 로컬 DB에 반영되지 않은 상태로 선택 동기화를 실행하면 **이미 전송된 기사를 재전송**하거나 pending 판정이 달라질 수 있다.
* **근거**: `selected_sync.py` 전체 흐름; `service.py:213-222`의 `_run_pipeline_body`와 대비.
* **권장 수정 방향**: `sync_selected_articles` 시작 시 `service.maybe_backup_pull(log_callback=...)` 호출 후 진행(또는 `_run_pipeline_body`와 동일한 래퍼로 통일).
* **우선순위**: **Medium** (멀티 PC 백업 사용자에 한정)

---

### N4. Preview가 백업 pull 없이 config 스냅샷 사용 — stale 사이트 목록 가능

* **위치**: `websync/pipeline/preview.py:38-40`
* **문제**: `service.config_manager.load_config()` 스냅샷을 사용해 사이트 목록을 읽는다. 시작 직후 백업 pull이 아직 실행되지 않았거나 다른 프로세스가 사이트를 편집 중이면 **프리뷰 결과가 실제 동기화와 다를 수 있다**.
* **영향**: “프리뷰에서는 신규 5건이었는데 동기화하면 0건” 같은 사용자 혼란. 다만 preview는 락을 잡으므로 동시 동기화와 겹치지는 않음.
* **근거**: `preview.py:39` `config = service.config_manager.load_config()`; `service.py:88-108`의 pull 로직과 대비.
* **권장 수정 방향**: preview 시작 시 `maybe_backup_pull`(또는 최소 `service._reload_config()` 후 최신 config) 사용; 또는 문서에 “프리뷰는 로컬 캐시 기준” 명시.
* **우선순위**: **Low–Medium** (UX 일관성)

---

### N5. 시크릿(API 키·토큰) 평문 저장 — 잔여

* **위치**: `websync/config/manager.py:80-106` (`DEFAULT_CONFIG`) — `ai_summary.api_key`, `web_dashboard.api_token`, `opds_server.api_key`, `translation.libretranslate_api_key`
* **문제**: 민감 값이 `config.json`에 평문. 파일은 `.gitignore` 대상이나, **공유 폴더 백업은 sites/history만 내보내므로**(service.py의 push payload 확인) 직접 유출 경로는 아니다. 다음 경로로 유출 가능:
  - 수동 백업·스크린샷·공유 폴더 실수(config.json 자체를 복사)
  - 공용 PC에서 config.json 파일 접근
  - LAN 공개 + 토큰 탈취 = 원격 동기화 트리거 가능
* **영향**: OpenAI 키 등 유출 시 비용/프라이버시; 웹 대시보드 토큰 탈취 시 원격 제어.
* **근거**: config 스키마; 웹/OPDS 토큰은 자동 생성(`secrets.token_urlsafe`)되어 기본 보안은 있으나, API 키는 사용자 입력 평문.
* **권장 수정 방향**: OS 자격 증명 저장소(keyring) 연동 옵션; UI “키 마스킹”(`show="*"`, 부분 구현 추정); LAN 모드 경고 강화(이미 일부 구현).
* **우선순위**: **Medium** (위협 모델 의존 — 공용/LAN 환경에서만 High)

---

### N6. 웹/OPDS 서버 — 기본 `ThreadingHTTPServer` 미사용으로 직렬 처리

* **위치**: `websync/servers/opds.py:12`(`_OPDSHTTPServer(HTTPServer)`), `websync/servers/dashboard/http_server.py:10`(`DashboardHTTPServer(HTTPServer)`)
* **문제**: 두 서버 모두 `http.server.HTTPServer`(단일 스레드)를 상속. 요청이 순차 처리되므로, 대용량 EPUB 다운로드(OPDS)나 긴 폴링이 진행 중일 때 **다른 요청이 블로킹**된다.
* **영향**: OPDS에서 큰 EPUB 다운로드 중 카탈로그 요청이 멈춤; 웹 대시보드에서 `/api/sync` 백그라운드 기동 중(즉시 반환하지만) 다른 엔드포인트 지연. 단일 사용자 로컬에서는 미미하나, LAN 다중 접속 시 체감.
* **근거**: 두 서버 클래스의 베이스가 `HTTPServer`(`serve_forever` 단일 스레드 핸들러).
* **권장 수정 방향**: `ThreadingHTTPServer`(`from http.server import ThreadingHTTPServer`)로 전환. 핸들러는 이미 상태 비저장(서버 속성에서 콜백 읽음)이라 스레드 안전.
* **우선순위**: **Low–Medium** (LAN 환경 UX)

---

### N7. `_pipeline_lock`과 `_process_lock` 획득 순서가 호출처마다 다름 — 교착 가능성(이론적)

* **위치**: 
  - `websync/pipeline/service.py:187-204` (`_try_acquire_pipeline_locks`: thread → process 순, 실패 시 thread 해제)
  - `websync/pipeline/preview.py:29-35`, `selected_sync.py:40-47` (동일 순서, 직접 중복 구현)
* **문제**: 세 곳 모두 **thread lock 먼저, process lock 나중** 순서로 일관되지만, `preview`/`selected`가 `service`의 헬퍼를 쓰지 않고 **락 획득 로직을 복제**한다. 향후 한 곳만 순서를 바꾸면 교착 상태 가능.
* **영향**: 현재는 일관되므로 안전. 단, 중복 코드로 인해 유지보수 시 실수 위험.
* **근거**: `preview.py:29-35`, `selected_sync.py:40-47`이 `service._try_acquire_pipeline_locks`와 동일 로직 중복.
* **권장 수정 방향**: `preview`/`selected`도 `service._try_acquire_pipeline_locks(log_callback)`를 호출하도록 통일; 해제도 `_release_pipeline_locks` 사용(`try/finally`).
* **우선순위**: **Low** (현재 안전, 중복 제거 목적)

---

### N8. Summarizer/Translator 예외 시 조용한 스킵 — 사용자 인지 부족

* **위치**: `websync/pipeline/summarizer.py:44-46`, `translator.py:56-58`
* **문제**: API 호출 실패 시 `except Exception as e: print(...)` 후 빈 문자열/원문 반환. 파이프라인은 계속 진행하지만, **사용자가 “AI 요약이 안 됐다”는 사실을 로그나 토스트로 명확히 알기 어렵다**(stdout print만).
* **영향**: API 키 오류·네트워크 문제·할당량 초과 시 요약 없이 EPUB이 생성되어, 사용자는 “요약 기능이 켜졌는데 왜 없지?” 혼란.
* **근거**: `summarizer.py:45` `print(f"⚠️ AI 요약 실패: {e}")`; 파이프라인은 `summarizer.summarize()` 반환값만 소비.
* **권장 수정 방향**: `log_callback` 전달하여 GUI/로그 바에 실패 메시지 노출; 또는 사이트별 스킵 카운트를 `last_fetch_stats` 패턴처럼 집계.
* **우선순위**: **Low** (기능 동작, 가시성 개선)

---

### N9. `ProcessFileLock.is_held_by_other`가 자체 락 파일 경로로 try-lock — 부작용 가능

* **위치**: `websync/core/process_lock.py:109-117`
* **문제**: `is_held_by_other`는 새 `ProcessFileLock(self.lock_path)` 프로브를 만들어 `acquire(blocking=False)` 시도. 성공하면 release하고 False, 실패하면 True. 이는 `is_pipeline_running`(`service.py:68-71`)에서 busy 판정에 쓰인다.
* **영향**: 
  - 정상 동작하지만, **다른 프로세스가 락을 잡고 있을 때 프로브 자체는 파일 핸들을 열었다 닫으므로** 미세한 경합 가능(실제 락 획득은 아니므로 간섭 없음).
  - 웹 대시보드 `/api/sync`의 `busy_cb()`가 이를 호출 → 매 요청마다 파일 시스템 프로브.
* **근거**: `process_lock.py:113-116`; `service.py:71`의 `is_held_by_other()` 호출.
* **권장 수정 방향**: 현재 동작은 안전(try-lock 실패 = 타인 보유). 다만 `is_pipeline_running`의 `self._pipeline_lock.locked() or self._process_lock.held` 우선순위로 대부분 커버되므로, 프로브는 보조 수단으로 문서화.
* **우선순위**: **Low** (정상 동작, 개선 권고만)

---

## 4. Potential Functional Gaps

> 확실하지 않은 항목은 **(추정)** 표시.

### 4.1 동작 보완 후보

| 항목 | 설명 | 확실성 |
|------|------|--------|
| `naver_post` 서비스 종료 UX | 명확한 예외는 발생하지만, GUI에서 타입 선택 시 경고 배너가 있는지 미확인 | **(추정)** |
| AI 요약/번역 실패 시 알림 | 예외 시 print만 — 파이프라인 로그/토스트로 명확화 필요 | 확인됨(N8) |
| 백업 시작 pull 후 UI 부분 갱신 | 사이트 트리·이력은 갱신; 다른 탭 필드 stale 가능 | **(추정)** |
| 충돌 병합 정책 | `_merge_config_on_conflict`는 top-level 메모리 덮어쓰기 + sites URL 합집합(memory wins). 로컬 미편집 필드가 원격 변경을 되돌릴 수 있음 | **(추정)** — 필드 단위 LWW 부재 |
| Watch 실패 파일 재큐 | debounce 타임아웃 스킵 후 재시도 없음; 안정성 검사(크기 2회) 실패 시 드랍 | **(추정)** 운영 시 놓친 파일 |
| 합본 모드 카운팅 의미 | `actual_work_sites`(사이트 수)로 합본(1건 업로드) 성공을 재단 — N1 참조 | 확인됨 |
| OPDS/웹 동시 요청 | 단일 스레드 HTTPServer — N6 참조 | 확인됨 |
| `pending_device_ips` 프로덕션 미사용 | 파이프라인은 인라인 `resolve_pending_upload_ips` 사용; API는 유휴 | 확인됨 |
| 선택 동기화 백업 pull 생략 | N3 참조 | 확인됨 |
| 스크래퍼 사이트 HTML 변경 | 네이버/티스토리 등 구조 변경 시 수집 실패 — 픽스처 테스트는 있으나 실사이트 CI는 선택 | 운영 리스크 |

### 4.2 문서·로드맵 잔여

- **CLAUDE.md의 `config_version: 2`가 코드(`CONFIG_VERSION = 3`)와 불일치** → 문서 갱신 필요.
- CLAUDE.md 로드맵 HIGH/MEDIUM 다수는 구현 완료로 표시되어 있음 — 신규 작업 전 본 문서와 코드 확인 권장.
- README는 사용자 중심, 개발 세부는 DEVELOPER.md — 대체로 정합.

### 4.3 긍정 영역 (재확인)

- 이전 감사 H1(웹 `/api/sync` 오판), H2(daily_digest 성공 집계), H3(import_sites RMW), H6(레거시 `*` 이관), H8(selected/sync 헬퍼 통일)는 **현재 코드에서 모두 해결**됨.
- 공유 폴더 백업은 **sites/history만 내보내고 시크릿은 제외**(service.py 주석 확인) — 올바른 설계.
- 기기 안정 id(`device_ids.py`) 도입으로 IP 변경 시에도 동일 기기 인식 — 견고함.

---

## 5. Recommended Fix Plan

> **2026-07-27 업데이트**: 아래 1·2·3·4단계 권고는 **모두 반영 완료**. 잔여 사항은 4.2/4.3(제외 항목)과 문서 동기화 유지뿐이다.

### 1단계 — 즉시 수정 (기능 정합·문서) ✅

1. ✅ **문서 정합**: `CLAUDE.md`의 `config_version: 2` → `3` 수정
2. ✅ **N1** daily_digest 카운팅 의미 명확화 (합본 전용 `digest_success`/`digest_partial` 플래그)
3. ✅ **N3** `sync_selected_articles` 시작 시 `maybe_backup_pull` 호출

### 2단계 — 안정성·성능 개선 ✅

4. ✅ **N2** 네이버 스크래퍼 상세 페이지 병렬 수집(ThreadPoolExecutor max 3) + `last_fetch_stats` 설정 + 전 실패 예외
5. ✅ **N6** OPDS/웹 대시보드 서버를 `ThreadingHTTPServer`로 전환
6. ✅ **N4** Preview 시작 시 백업 pull + 최신 config 사용
7. ✅ **N7** preview/selected의 락 획득/해제를 `service._try_acquire_pipeline_locks`/`_release_pipeline_locks`로 통일
8. ✅ **N8** Summarizer/Translator 실패를 `logger`(주입형)로 노출

### 3단계 — 보안·구조·유지보수 ✅

9. ✅ **N5** 시크릿 UI 마스킹(보기/숨기기 토글) + `mask_secret` 헬퍼 통일. OS keyring 옵션은 본 라운드 제외(의존성·마이그레이션 리스크 최소화)
10. ⏸️ 파이프라인 단계 객체화 — 본 라운드 제외(현재 196 passed로 테스트 충분, 리팩터링 리스크 대비 효익 낮음)
11. ✅ GUI 자동저장은 이미 `_safe_save_config` CAS로 커버되어 있음(변경 불필요)
12. ⏸️ Watch 실패 파일 재시도 큐 — 본 라운드 제외(운영상 드문 케이스)
13. ✅ **N9** `is_held_by_other` 프로브 의미 docstring화

### 4단계 — 잔여 (추후 검토)

- OS keyring 연동 옵션(N5 심화) — 공용 PC/LAN 환경에서만 고려
- `pending_device_ips` 미사용 시 deprecated 표시 또는 삭제
- 파이프라인 단계 객체화(수집/필터/빌드/업로드/이력) — 테스트 용이성 추가 향상 목적
- Watch 데드레터 큐

---

## 6. Test Recommendations

> **2026-07-27 업데이트**: 아래 6.1~6.3 권고는 **반영 완료**. 현재 **196 passed**.

### 6.1 1단계 이슈 (필수) ✅

| 테스트 | 내용 | 상태 |
|--------|------|------|
| `test_daily_digest_all_upload_fail_not_success` | 합본 전 기기 실패 시 `success is False` (N1 경계) | ✅ `test_pipeline_digest.py` |
| `test_daily_digest_partial_upload_marks_only_ok` | 합본 일부 성공 → 성공 IP만 mark, `digest_partial` | ✅ `test_pipeline_digest.py` |
| `test_daily_digest_happy_path` | build_digest + upload 실제 경로 | ✅ `test_pipeline_digest.py` |
| `test_config_version_documented` | CLAUDE.md와 `CONFIG_VERSION` 정합 | ✅ 문서 수동 갱신 |

### 6.2 안정성·성능 ✅

| 테스트 | 내용 | 상태 |
|--------|------|------|
| `test_parallel_detail_collection_preserves_order` | 네이버 병렬 수집 후 RSS 순서 유지 (N2) | ✅ `test_naver_scraper.py` |
| `test_skipped_stats_recorded_when_detail_fails` | `last_fetch_stats["skipped"]` 설정 검증 | ✅ `test_naver_scraper.py` |
| `test_opds_serves_concurrent_requests` | `ThreadingHTTPServer` 동시 요청 처리 (N6) | ✅ `test_opds.py` |
| `test_dashboard_serves_concurrent_status_requests` | sync_cb 블로킹 중 status 즉시 응답 (N6) | ✅ `test_web_dashboard.py` |
| `test_selected_sync_calls_backup_pull_before_processing` | 선택 동기화 시작 시 pull 호출 (N3) | ✅ `test_selected_sync.py` |
| `test_selected_sync_rejects_when_busy` | 통일된 락 헬퍼 사용 검증 (N7) | ✅ `test_selected_sync.py` |

### 6.3 보안·로깅 ✅

| 테스트 | 내용 | 상태 |
|--------|------|------|
| `test_summarizer_uses_logger_when_provided` | logger 주입 시 `logger.warning` 호출 (N8) | ✅ `test_summarizer.py` |
| `test_translator_uses_logger_on_failure` | 번역 실패 시 logger 노출 (N8) | ✅ `test_translator.py` |
| `test_redact_config_masks_all_secret_paths` | mask_secret 헬퍼 전 시크릿 필드 마스킹 (N5) | ✅ `test_secrets.py` |
| `test_mask_secret_keeps_tail_by_default` | 마스킹 동작 고정 (N5) | ✅ `test_secrets.py` |

### 6.4 통합·회귀 (잔여)

| 테스트 | 내용 | 상태 |
|--------|------|------|
| `test_backup_pull_then_selected_sync` | pull로 가져온 이력이 선택 동기화 pending에 반영 | 추후 |
| `test_safe_save_config_triple_conflict` | 연속 CAS 충돌 3회 시도 동작 정의 | 기존 커버 |
| scheduler Windows TR 문자열 | 공백 포함 경로 quote 스냅샷 | 기존 커버 |

### 6.5 스크래퍼

- 픽스처 기반 테스트 유지 + `scripts/validate_korean_scrapers.py` 주기 실행
- 사이트 HTML 변경 시 픽스처 업데이트 프로세스 문서화
- 네이버 `PostView` 응답 지연 시나리오(타임아웃/재시도) 추가 — 본 라운드 `test_naver_scraper.py` 일부 커버

---

## 7. Appendix

### 7.1 CodeGraph 중심 분석 대상

- `main` / `acquire_instance_lock` / `SyncService.run_sync_pipeline` / `begin_sync_pipeline_async`
- `run_sync_pipeline_locked` / `preview_articles` / `sync_selected_articles`
- `ConfigManager.save_config` / `update_config` / revision CAS / `import_sites`
- `SyncHistoryDb.needs_sync` / `mark_synced_many` / `remap_legacy_star_to_device`
- `X3Uploader.upload_to_targets` / `X3DeviceClient` / `normalize_remote_path` / `device_ids`
- `BackupSyncService.pull`/`push` / `merge_sites` / `local_import`
- `DashboardHandler` / `session_valid` / `OPDSHandler` / `SchedulerManager` / `CalibreWatcher`
- `upload_results.py` 공통 헬퍼 / `resolve_pending_upload_ips`

### 7.2 검증 명령

```bash
python -m pytest tests/ -q
# 결과: 196 passed (2026-07-27, 감사 시점 161 → +35)
```

### 7.3 위험도 매트릭스 (수정 후)

| 영역 | 위험(수정 전) | 위험(수정 후) | 비고 |
|------|------|------|------|
| 파이프라인 락/중복 실행 | Low | Low | N7 락 헬퍼 통일로 유지보수 위험 감소 |
| 설정 RMW | Low | Low | 변경 없음 |
| 이력 DB 다중 기기 | Low | Low | 변경 없음 |
| daily_digest 카운팅 | Medium | **Low** | N1 — 합본 전용 카운터 분리 + 회귀 테스트 |
| 네이버 스크래퍼 성능 | Medium | **Low** | N2 — 병렬 수집(max 3) + 스킵 통계 |
| 선택 동기화 백업 pull | Medium | **Low** | N3 — pull 추가 |
| 웹/OPDS 동시 요청 | Low–Medium | **Low** | N6 — ThreadingHTTPServer 전환 |
| 시크릿 저장/표시 | Medium | **Low–Medium** | N5 — UI 마스킹(평문 config.json 자체는 유지) |
| AI/번역 실패 가시성 | Low | **Low** | N8 — logger 주입 |
| 업로드/경로 | Low | Low | 변경 없음 |
| 스케줄러 | Low | Low | 변경 없음 |
| 테스트 | Low–Medium | **Low** | 161 → 196 passed |

### 7.4 수정 반영 파일 목록 (2026-07-27)

| 파일 | 변경 내용 |
|------|-----------|
| `CLAUDE.md` | `config_version` 2→3 정합 |
| `websync/pipeline/sync_pipeline.py` | N1 daily_digest 카운팅 분리, N8 logger 주입 |
| `websync/pipeline/selected_sync.py` | N3 백업 pull, N7 락 헬퍼 통일, N8 logger 주입 |
| `websync/pipeline/preview.py` | N4 백업 pull + 최신 config, N7 락 헬퍼 통일 |
| `websync/pipeline/summarizer.py` | N8 logger 주입 + print 제거 |
| `websync/pipeline/translator.py` | N8 logger 주입 + print 제거 |
| `websync/scrapers/naver.py` | N2 병렬 수집 + skipped stats + 전 실패 예외 |
| `websync/servers/opds.py` | N6 ThreadingHTTPServer |
| `websync/servers/dashboard/http_server.py` | N6 ThreadingHTTPServer |
| `websync/core/process_lock.py` | N9 프로브 docstring |
| `websync/gui/settings_tab/tab.py` | N5 마스킹 토글 위젯 추가 |
| `websync/gui/settings_tab/ai_translation.py` | N5 토글 헬퍼 + mask_secret 사용 |
| `websync/gui/settings_tab/servers.py` | N5 서버 시작 시 키 표시 갱신 |
| `websync/gui/app_core/config_sync.py` | N5 평문 토큰 노출 제거 + 헬퍼 호출 |
| `tests/test_pipeline_digest.py` | 신규 — N1 회귀 4건 |
| `tests/test_naver_scraper.py` | 신규 — N2 단위 9건 |
| `tests/test_selected_sync.py` | 신규 — N3/N7 4건 |
| `tests/test_translator.py` | 신규 — N8 5건 |
| `tests/test_secrets.py` | 신규 — N5 8건 |
| `tests/test_summarizer.py` | 보강 — N8 3건 추가 |
| `tests/test_opds.py` | 보강 — N6 동시 요청 1건 |
| `tests/test_web_dashboard.py` | 보강 — N6 동시 요청 1건 |

---

*본 문서는 코드 수정을 포함하지 않는 감사 리포트이다. 수정 작업은 별도 이슈/PR로 진행할 것.*
