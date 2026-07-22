# Project Audit

> **감사 일자**: 2026-07-22  
> **수정 반영**: 2026-07-22 — 아래 High/Medium 권고 대부분 코드·테스트 반영 (`pytest` **151 passed**)  
> **감사 관점**: 기능 구현 — 동시성, 예외 처리, 데이터 흐름, 보안, 경로/인코딩, 설정·DB, 테스트, 문서 정합  
> **방법**: `README.md` / `CLAUDE.md` 숙지 → **CodeGraph MCP**로 진입점·호출 관계·영향 범위 분석 → 필요 시 소스 직접 확인·`pytest` 실행  
> **검증**: `python -m pytest tests/ -q` → **151 passed** (감사 시점 138 → 수정 후 151)  
> **참고**: `docs/PROJECT_AUDIT.md`(2026-07-14)는 구버전 아카이브. 이전 루트 감사(2026-07-20) 이후 코드 수정 반영 여부를 재확인한 **전면 재감사**입니다.

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 CrossPoint e-ink 기기를 위한 뉴스·콘텐츠 수집 → EPUB 빌드 → 무선 전송 데스크톱 앱입니다. SOLID 기반 패키지 분리, 스레드/프로세스 파이프라인 락, config 원자 저장 + revision CAS, 기기별 SQLite 이력, OPDS·웹 대시보드 인증, 클라우드 폴더 백업(`websync/backup`)까지 갖춘 **성숙도 높은** 코드베이스입니다.

- **전체 위험도**: **Medium-Low** (개인 PC·로컬 LAN 가정)  
  - LAN 공개(`allow_lan`)·멀티 PC 백업 동기화·API 키 평문 저장을 쓰는 환경에서는 **Medium**
- **테스트 현황**: 단위/통합 테스트 **138 passed** — 핵심 파이프라인·DB·업로더·백업·대시보드 일부가 커버됨
- **이전 감사 대비**: 스케줄 경로 공백 인용, 프리뷰 락 획득, 레거시 `device_ip='*'` 전 기기 완료 취급 제거, backup `auto_export` 가드, OPDS 청크 전송, `_last_pipeline_result` 인스턴스 변수, Watch 큐+타임아웃 등은 **현재 코드에서 해결 또는 완화**됨

### 핵심 이슈 처리 현황 (2026-07-22 수정 반영)

| 순위 | 이슈 | 우선순위 | 상태 |
|------|------|----------|------|
| 1 | 웹 대시보드 `POST /api/sync` 항상 202 | **High** | ✅ `begin_sync_pipeline_async` + False→409 |
| 2 | daily_digest 대상 없음 성공 집계 | **High** | ✅ 기기 0대 early `no_targets`; digest pending 없음=이미 전송 |
| 3 | `import_sites` RMW 덮어쓰기 | **Medium** | ✅ `update_config` 합집합 |
| 4 | `_safe_save_config` 재시도 1회 | **Medium** | ✅ 최대 3회 병합 재시도 |
| 5 | API 키 평문 저장 | **Medium** | 부분 — `secrets.mask` 유틸·AI 키 UI `show=*`(기존) / OS keyring 은 미구현 |
| 6 | 레거시 `*` 자동 이관 | **Low–Medium** | ✅ 파이프라인 시작 시 기본 기기로 remap |
| 7 | `pending_device_ips` 빈 대상 | **Low** | ✅ 명시적 `[]` + 테스트 |
| 8 | selected_sync / upload 판정 불일치 | **Medium** | ✅ `upload_results` 헬퍼 공통화 |
| 9 | macOS plist XML 이스케이프 | **Low** | ✅ `_xml_escape` |
| 10 | GUI·Watch E2E 테스트 부족 | **Medium** | 잔여 (유지보수) |

**과장하지 않은 총평**: 치명적(Critical) 보안 구멍이나 데이터 파괴 버그는 확인되지 않았다. 다만 **원격 동기화 트리거 UX 오판**과 **합본 모드 성공 판정 오류**는 실제 사용자 혼란·스케줄/자동화 오동작을 유발할 수 있다.

---

## 2. Project Understanding

### 2.1 목적 (README / CLAUDE)

| 항목 | 내용 |
|------|------|
| 목적 | Xteink X3용 뉴스·블로그 수집 → e-ink 최적 EPUB → 무선 전송 자동화 |
| 핵심 가치 | SQLite 증분 동기화(기기별), 다중 사이트/기기, Calibre·OPDS·웹 대시보드·스케줄·백업 |
| 원칙 | SOLID, 모듈 단일 책임, 타입 힌트 |
| 진입 | `python x3_websync.py` (GUI) / `--sync` (스케줄·백그라운드) |

### 2.2 패키지 구조 (현재 코드 기준)

```
x3_websync.py                 # CLI/GUI, GUI 단일 인스턴스 락
websync/
  core/                       # paths, process_lock, logger, article
  config/                     # manager, validator, exceptions
  db/                         # SyncHistoryDb (기기별 PK)
  scrapers/                   # 13종 + factory/types/presets
  epub/                       # builder, css, cover, sanitize, themes
  upload/                     # uploader, device_client, host, remote_path
  pipeline/                   # SyncService + sync/preview/selected/AI
  backup/                     # 클라우드 폴더 sites/history JSON pull/push
  integrations/               # Calibre, ToastNotifier
  scheduler/                  # schtasks / launchd / crontab
  servers/                    # OPDS + dashboard/
  watch/                      # CalibreWatcher
  gui/                        # app_core, sync_tab, device_files, settings_tab
```

### 2.3 주요 실행 흐름 (CodeGraph)

```
main()
  ├─ [GUI] acquire_instance_lock()  # Windows mutex + 락 파일 / Unix flock
  ├─ ConfigManager() → SyncService(config_manager)
  │     ├─ SyncHistoryDb
  │     └─ BackupSyncService
  ├─ [--sync]
  │     run_sync_pipeline()
  │       ├─ _pipeline_lock + ProcessFileLock (비차단)
  │       ├─ maybe_backup_pull()
  │       ├─ run_sync_pipeline_locked()
  │       │     scrape → needs_sync → translate/summarize
  │       │     → build / build_digest → upload_to_targets(only_ips)
  │       │     → mark_synced_many(성공 IP만)
  │       └─ maybe_backup_push()
  └─ [GUI] SyncAppGui
        ├─ 시작 300ms 후 백그라운드 maybe_backup_pull
        ├─ 탭: 동기화 / Calibre / 이력 / 기기 파일 / 고급 설정
        └─ Watch 큐 워커 / OPDS / 웹 대시보드
```

### 2.4 동시성·데이터 계층

| 계층 | 메커니즘 | 상태 |
|------|----------|------|
| GUI 단일 실행 | named mutex + 락 파일 / flock | 양호 |
| 파이프라인 | `SyncService._pipeline_lock` + `ProcessFileLock` | 양호; 프리뷰·선택 동기화도 동일 락 사용 |
| Config | `ConfigManager._lock` + tmp/bak/replace + `_config_revision` CAS | GUI는 `_safe_save_config`로 CAS 사용 |
| DB | `SyncHistoryDb._db_lock` + `sqlite3` timeout=10s | 양호 |
| 업로드 | `ThreadPoolExecutor` (기기 병렬, max 4) | 양호 |
| 백업 폴더 | 스레드 Lock + `.backup_sync.lock` | 양호 |
| Watch | 단일 워커 큐 + 락 acquire **timeout=30s** | 이전 무한 대기 이슈 해결 |

### 2.5 문서·구현 정합

| 항목 | 문서 | 코드 | 정합 |
|------|------|------|------|
| 스크래퍼 수 | CLAUDE/README 13종 | `SCRAPER_TYPES` 13종 | 일치 |
| 백업 패키지 | CLAUDE 구조에 `backup/` | `websync/backup/` 존재 | 일치 |
| 프로세스 락 | CLAUDE 기술 | `ProcessFileLock` 사용 | 일치 |
| 레거시 `*` | CLAUDE: 마이그레이션 시 `*` 부여 | `is_synced_for_device`는 `*`를 전 기기 완료로 **취급하지 않음** | **문서가 “모든 기기 완료”로 읽히면 구버전** — 구현이 수정됨 |
| 테스트 수 | 이전 감사 117 collect | 현재 **138 passed** | 문서 갱신 필요(본 파일) |

### 2.6 이전 감사(2026-07-14/20) 대비 해결 확인

| 과거 이슈 | 현재 상태 |
|-----------|-----------|
| Windows 스케줄 `cd /d` 경로 미인용 | `_win_quote` + `build_windows_tr_command`로 공백 안전 |
| 프리뷰 TOCTOU (검사만 하고 락 미획득) | `preview.py`에서 비차단 락 획득 |
| 레거시 `*` = 전 기기 완료 | `is_synced_for_device`가 IP 정확 일치만 사용 |
| backup `push`의 `auto_export` 무시 | `_push_unlocked`에서 `auto_export` 검사 |
| OPDS 전체 메모리 로드 | 64KB 청크 전송 |
| EPUB `set_identifier` 누락 | `build()`에 설정됨 |
| Watch 스레드 무한 누적/무한 락 대기 | 큐 워커 + 30초 타임아웃 |
| `_last_pipeline_result` 클래스 변수 | 인스턴스 변수 + 테스트 존재 |

---

## 3. High-Risk Issues

### H1. 웹 대시보드 동기화 API 성공 응답이 실제 기동과 불일치

* **위치**: `websync/servers/dashboard/handler.py` — `DashboardHandler.do_POST` (`/api/sync`)
* **문제**: `pipeline_busy_callback`으로 사전 검사는 하지만, 백그라운드 스레드를 기동한 뒤 **즉시 202 + `{"ok": true}`** 를 반환한다. `started` dict에 결과를 넣지만 **응답 전에 읽지 않는다**. `run_sync_pipeline`이 락 실패로 `False`를 반환해도 클라이언트는 성공으로 인식한다.
* **영향**: 원격/브라우저에서 “동기화 시작됨”으로 오판; 연속 클릭·자동화 스크립트가 실패를 놓침; `/api/status`만으로는 즉시 실패를 알기 어려움.
* **근거**:
  ```python
  # handler.py (요약)
  def _run():
      result = sync_cb()
      started["ok"] = bool(result) if result is not None else True
  threading.Thread(target=_run, daemon=True).start()
  self._send_json(202, {"ok": True, "message": "✅ 동기화가 백그라운드에서 시작됩니다."})
  ```
* **권장 수정 방향**:
  1. 스레드 기동 전 `run_sync_pipeline`과 동일하게 락을 **짧게 선점**하거나, 기동 직후 짧은 시간 내 “락 획득 성공” 이벤트를 기다린 뒤 202/409 결정  
  2. 또는 202를 “수락(accepted)”으로만 쓰고 `ok`/`started`를 별도 필드로 두며, 실패 시 클라이언트가 `/api/status`를 폴링하도록 계약 문서화  
  3. 테스트: 락 점유 중 `/api/sync`가 최종적으로 실패 상태를 드러내는지 검증 (현재 `test_api_sync_busy_response`는 busy 콜백만 409)
* **우선순위**: **High**

---

### H2. daily_digest 모드에서 “전송 대상 없음”을 성공으로 집계

* **위치**: `websync/pipeline/sync_pipeline.py` — `run_sync_pipeline_locked` daily_digest 분기
* **문제**: `pending_ips`가 비어 있을 때 합본 생성/업로드를 건너뛴 뒤 `success_count = actual_work_sites`로 설정한다. 이후 `overall_ok = success_count == actual_work_sites and site_errors == 0`이므로 **True(성공)** 가 된다.  
  (비교: `per_site` 모드는 pending 없으면 `continue`만 하고 success를 올리지 않아, 작업이 있었으면 실패 쪽으로 기운다.)
* **영향**: 기기 미등록·주소 오류·모든 기기가 이미 전송된 것으로 오판된 상태에서 스케줄러/`--sync`가 exit 0; 토스트/요약이 “완료”처럼 보일 수 있음. 이력(`mark_synced`)은 안 남으므로 재시도는 되지만 **성공 신호는 거짓**이다.
* **근거**:
  ```python
  # sync_pipeline.py ~249-251
  else:
      log("💡 전송할 대상 기기가 없어 합본 생성을 건너뜁니다.")
      success_count = actual_work_sites
  ```
* **권장 수정 방향**:
  - “이미 모든 기기 전송 완료”와 “등록 기기 0대”를 분리  
  - 기기 0대 → `success=False`, status=`no_targets`  
  - 이미 전부 전송 → `success=True`, status=`no_new` (또는 digests 스킵 전용 상태)  
  - 단위 테스트 추가
* **우선순위**: **High**

---

### H3. `import_sites`의 RMW 레이스 (revision CAS 미사용)

* **위치**: `websync/config/manager.py` — `ConfigManager.import_sites`
* **문제**: `load_config()` → 메모리에서 sites append → `save_config(config)` (**expected_revision 없음**). 그 사이 백업 pull·GUI 저장이 일어나면 **마지막 쓰기가 이김**.
* **영향**: 멀티 PC 백업 동기화 또는 GUI 자동저장과 겹치면 사이트 목록 일부가 사라질 수 있음.
* **근거**:
  ```python
  config = self.load_config()
  ...
  if added_sites:
      self.save_config(config)  # expected_revision 없음
  ```
* **권장 수정 방향**: `update_config(mutator)`로 디스크 최신본에 합집합 추가; 또는 `expected_revision` + 충돌 시 재병합.
* **우선순위**: **Medium**

---

### H4. GUI 설정 저장 충돌 재시도 1회 한계

* **위치**: `websync/gui/app_core/helpers.py` — `_safe_save_config`, `_merge_config_on_conflict`
* **문제**: CAS 충돌 시 disk+memory 병합 후 1회 재저장. 재저장 중 또 revision이 바뀌면 `ConfigConflictError`가 일반 예외 경로로 떨어져 **저장 실패 다이얼로그**만 표시.  
  또한 `_merge_config_on_conflict`는 top-level 키를 메모리로 덮어쓰고 sites는 URL 합집합(메모리 우선) — 의도적이나, 백업 pull이 가져온 원격 필드 변경이 **로컬 미편집 필드에 의해 되돌려질 수 있음**(추정 포함, 아래 Gaps).
* **영향**: 시작 직후 백업 pull + FocusOut 자동저장 경합 시 간헐적 저장 실패/의도치 않은 병합.
* **근거**: `_safe_save_config`의 `except ConfigConflictError` 블록 내 단일 재시도; 재시도 실패 시 상위 `except Exception`.
* **권장 수정 방향**: 짧은 루프 재시도(2–3회); 필드 단위 병합 정책 문서화; 가능하면 GUI 편집 필드를 `update_config` mutator로만 반영.
* **우선순위**: **Medium**

---

### H5. 시크릿 평문 저장 (API 키·대시보드 토큰)

* **위치**: `websync/config/manager.py` `DEFAULT_CONFIG` — `ai_summary.api_key`, `web_dashboard.api_token`, `opds_server.api_key`, `translation.libretranslate_api_key`
* **문제**: 민감 값이 `config.json`에 평문. 파일은 `.gitignore` 대상이나, 백업 폴더에 **sites만** 내보내는 것은 확인됨(sites payload). 로컬 백업·스크린샷·공유 폴더 실수 시 유출 가능.  
  OPDS/웹 토큰은 자동 생성(`secrets.token_urlsafe`)되어 기본 보안은 있음.
* **영향**: 공용 PC·동기화 폴더 오설정 시 OpenAI 키 등 유출. LAN 공개 시 토큰 탈취 = 원격 동기화 트리거 가능.
* **근거**: config 스키마 및 load 시 토큰 자동 생성; `backup` push는 sites/history 위주(시크릿 제외 주석 존재).
* **권장 수정 방향**: OS 자격 증명 저장소(keyring) 또는 별도 `secrets.json`(권한 제한); UI에 “키 마스킹”; LAN 모드 경고 강화.
* **우선순위**: **Medium** (위협 모델 의존)

---

### H6. 레거시 `device_ip='*'` 자동 이관 미실행

* **위치**: `websync/db/history.py` — `remap_legacy_star_to_device`; 호출부는 **테스트만**
* **문제**: 스키마 마이그레이션 시 구 이력은 `*`로 들어가지만, 런타임에 기본 기기 IP로 이관하는 코드는 **제품 경로에 없음**.  
  `is_synced_for_device`가 `*`를 무시하므로 **다중 기기 재전송 차단 문제는 해결**됨. 다만 `is_synced(url)` / `needs_sync(url, [])`는 여전히 `*` 행을 “이력 있음”으로 본다.
* **영향**: 기기 미설정 상태에서 프리뷰/동기화 신규 판정 왜곡 가능; DB에 고아 `*` 행 잔존.
* **근거**: CodeGraph/grep — `remap_legacy_star_to_device`는 `tests/test_db.py`만 참조.
* **권장 수정 방향**: 첫 기기 주소 확정 시 1회 자동 remap; 또는 GUI “레거시 이력 정리” 버튼.
* **우선순위**: **Low–Medium**

---

### H7. `pending_device_ips` 빈 대상 분기 논리 오류 (미사용 API)

* **위치**: `websync/db/history.py` — `pending_device_ips`
* **문제**:
  ```python
  if not target_ips:
      return [] if self.is_synced(url) else []  # 항상 []
  ```
* **영향**: 현재 프로덕션 호출자 없음(파이프라인은 인라인 pending 계산). 향후 이 API를 쓰면 “미전송 목록”이 항상 비어 보임.
* **권장 수정 방향**: 미사용이면 deprecated/삭제; 유지 시 의미 명확화 (예: 빈 target → `[]` 명시 문서 + 테스트).
* **우선순위**: **Low**

---

### H8. 선택 동기화의 `all_ok` 판정이 본 파이프라인보다 느슨함

* **위치**: `websync/pipeline/selected_sync.py`
* **문제**: `sync_pipeline`은 `set(upload_results) == set(pending_ips)`까지 검사. `selected_sync`는 `all(upload_results.values())`만 사용. 또한 성공 IP에 대해 **이미 동기화된 URL 필터 없이** 전 기사 `mark_synced_many`.
* **영향**: 업로드 결과가 일부 IP 누락 시(이론상) 과대 성공 판정; INSERT OR REPLACE로 `synced_at` 갱신.
* **근거**: `selected_sync.py` 107–108, 156–157행 대비 `sync_pipeline.py` 147행.
* **권장 수정 방향**: 본 파이프라인과 동일 헬퍼로 성공/이력 기록 공통화.
* **우선순위**: **Medium** (경계 조건)

---

### H9. 원격 경로/기기 HTTP는 평문 — 설계상 제약

* **위치**: `websync/upload/uploader.py`, `device_client.py`
* **문제**: `http://{host}/upload` 등 TLS 없음. CrossPoint 로컬 펌웨어 전제.
* **영향**: 동일 Wi-Fi 스니핑 시 EPUB 내용 노출 가능. 공용 Wi-Fi에서는 위험.
* **근거**: 업로드 URL 구성이 `http://` 고정.
* **권장 수정 방향**: 문서에 명시(이미 README 주의와 맥락 일치); 펌웨어 HTTPS 지원 시 옵션화.
* **우선순위**: **Low** (의도된 제약)

---

### H10. macOS launchd plist 경로 미이스케이프

* **위치**: `websync/scheduler/manager.py` — `_register_macos`
* **문제**: `script_path`/`project_dir`/`python_exe`를 XML 문자열에 보간. 경로에 `&`, `<` 등이 있으면 plist 손상 가능(로컬 사용자 경로 전제).
* **영향**: 특수문자 경로 사용자에서 스케줄 등록 실패.
* **권장 수정 방향**: XML escape 또는 plistlib 사용.
* **우선순위**: **Low**

---

## 4. Potential Functional Gaps

> 확실하지 않은 항목은 **(추정)** 표시.

### 4.1 동작 보완 후보

| 항목 | 설명 | 확실성 |
|------|------|--------|
| 기기 0대 early-exit | 스크래핑 전에 “등록 기기 없음”을 실패로 끊으면 네트워크·시간 절약 | **구현 공백 (코드상 확인)** |
| 부분 실패 자동 재시도 | 실패 IP만 다음 스케줄에서 재시도는 이미 됨; 같은 실행 내 재시도는 없음 | 의도일 수 있음 |
| 스크래퍼 사이트 HTML 변경 | 네이버/티스토리 등 구조 변경 시 수집 실패 — 픽스처 테스트는 있으나 실사이트 CI는 선택 | 운영 리스크 |
| `naver_post` 서비스 종료 | 명확한 예외 — GUI에서 타입 선택 시 경고 배너 있으면 시 UX 개선 | **(추정)** UI 미확인 |
| AI 요약/번역 실패 시 조용한 스킵 | 예외 시 print 후 원문/빈 요약 — 파이프라인은 계속 | 확인됨; 사용자 인지 부족 가능 |
| 백업 시작 pull 후 UI 부분 갱신 | 사이트 트리·이력만 갱신; 다른 탭 필드 stale 가능 | **(추정)** |
| 충돌 병합 정책 | 로컬 미저장 편집 + 원격 sites 병합 시 필드 단위 LWW 부재 | **(추정)** |
| Watch 실패 파일 재큐 | 30초 타임아웃 스킵 후 재시도 없음 | **(추정)** 운영 시 놓친 파일 |

### 4.2 문서·로드맵 잔여

- CLAUDE.md 로드맵 HIGH/MEDIUM 다수는 구현 완료로 표시되어 있음 — 신규 작업 전 루트 본 문서와 코드 확인 권장.
- README는 사용자 중심, 개발 세부는 DEVELOPER.md — 대체로 정합.

### 4.3 보안 방어가 잘 된 부분 (긍정)

- 웹 대시보드: Bearer/세션 HMAC, `secrets.compare_digest`
- OPDS: LAN 시 `require_auth`, path traversal `realpath` 검사, 쿼리 api_key 기본 비활성
- 원격 경로: `normalize_remote_path`가 `..` 제거
- 스케줄러: hour/minute 정수 검증, `shell=False` 인자 리스트
- Config: JSON 손상 시 `.corrupt` 보존

---

## 5. Recommended Fix Plan

### 1단계 — 즉시 수정 (기능 오판·자동화 영향)

1. **H1** `/api/sync` 응답 계약 수정 (락 실패 시 409/503, 또는 `started` 폴링 계약)  
2. **H2** daily_digest “대상 기기 없음” vs “이미 전송 완료” 분기 및 성공 판정 수정  
3. 위 두 항목 단위 테스트 추가 후 `pytest` 회귀

### 2단계 — 안정성 개선

4. **H3** `import_sites` → `update_config` RMW  
5. **H4** `_safe_save_config` 재시도 루프 + 병합 정책 문서화  
6. **H8** `selected_sync`와 `sync_pipeline`의 upload/mark 헬퍼 공통화  
7. 기기 0대 early validation (파이프라인 시작 시 명확한 실패 메시지)  
8. **H6** 첫 기기 연결 시 레거시 `*` remap 옵션

### 3단계 — 구조·보안·유지보수

9. **H5** 시크릿 저장 분리 / 마스킹 UI  
10. 파이프라인 단계 객체화(수집/필터/빌드/업로드/이력)로 테스트 용이성 향상  
11. GUI 자동저장을 mutator 기반으로 전환해 인메모리 전체 dict 덮어쓰기 축소  
12. macOS plist XML escape, Watch 실패 재시도 큐  
13. 문서(CLAUDE 레거시 `*` 설명, 본 감사 일자) 동기화

---

## 6. Test Recommendations

현재 **138 passed**. 아래는 커버 공백이 큰 영역이다.

### 6.1 필수 추가 (1단계 이슈)

| 테스트 | 내용 |
|--------|------|
| `test_api_sync_reports_lock_failure` | 파이프라인 락 점유 중 `/api/sync`가 성공으로 끝나지 않거나 status로 실패 확인 가능 |
| `test_daily_digest_no_devices_not_success` | `x3_ip` 비어 있고 devices 없을 때 digest 모드 → `success is False` |
| `test_daily_digest_all_already_synced` | pending 없음 + 이력 있음 → no_new 계열 성공 또는 명시적 스킵 |

### 6.2 안정성

| 테스트 | 내용 |
|--------|------|
| `test_import_sites_concurrent_with_update` | pull/update_config와 겹쳐도 sites 유실 없음 |
| `test_safe_save_config_double_conflict` | 연속 CAS 충돌 시 동작 정의(재시도 또는 명확한 에러) |
| `test_selected_sync_partial_upload_marks_only_ok` | `sync_pipeline` partial 테스트와 동일 시나리오 |
| `test_pending_device_ips_empty_targets` | API 유지 시 기대 동작 고정 |

### 6.3 통합·회귀

| 테스트 | 내용 |
|--------|------|
| `run_sync_pipeline_locked` happy path | mock scraper + mock upload + 실제 temp DB |
| preview + sync 직렬화 | 프리뷰 중 sync 비차단 실패 |
| backup pull → GUI save | revision 증가 후 `_safe_save_config` 병합 |
| scheduler Windows TR 문자열 | 공백 포함 경로 quote 스냅샷 (이미 일부 존재 시 보강) |
| OPDS path traversal | `../` 파일명 요청 403 |

### 6.4 스크래퍼

- 픽스처 기반 테스트 유지 + `scripts/validate_korean_scrapers.py` 주기 실행  
- 사이트 HTML 변경 시 픽스처 업데이트 프로세스 문서화

---

## 7. Appendix

### 7.1 CodeGraph 중심 분석 대상

- `main` / `acquire_instance_lock` / `SyncService.run_sync_pipeline`
- `run_sync_pipeline_locked` / `preview_articles` / `sync_selected_articles`
- `ConfigManager.save_config` / `update_config` / revision CAS
- `SyncHistoryDb.needs_sync` / `mark_synced_many` / legacy `*`
- `X3Uploader.upload_to_targets` / `DeviceClient` / `normalize_remote_path`
- `BackupSyncService.pull`/`push` / `merge_sites`
- `DashboardHandler` / `OPDSHandler` / `SchedulerManager` / `CalibreWatcher`

### 7.2 검증 명령

```bash
python -m pytest tests/ -q
# 결과: 138 passed (2026-07-22)
```

### 7.3 위험도 매트릭스 (요약)

| 영역 | 위험 | 비고 |
|------|------|------|
| 파이프라인 락/중복 실행 | Low | 스레드+프로세스 락 견고 |
| 설정 RMW | Medium | GUI CAS 양호, import_sites 취약 |
| 이력 DB 다중 기기 | Low–Medium | `*` 전 기기 완료 버그 수정됨; 고아 행만 잔존 |
| 웹/OPDS 인증 | Low–Medium | 구현 양호; LAN+토큰 유출 시 동기화 트리거 |
| 업로드/경로 | Low | sanitization·path normalize 있음 |
| 스케줄러 | Low | Windows quote 수정됨 |
| 테스트 | Medium | 단위 양호, 일부 통합/경계 부족 |

---

*본 문서는 코드 수정을 포함하지 않는 감사 리포트이다. 수정 작업은 별도 이슈/PR로 진행할 것.*
