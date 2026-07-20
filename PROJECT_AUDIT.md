# Project Audit

> **감사 일자**: 2026-07-20  
> **감사 관점**: 기능 구현 — 동시성, 예외 처리, 데이터 흐름, 보안, 경로/인코딩, 설정·DB, 테스트, 문서 정합  
> **방법**: `README.md` / `CLAUDE.md` 숙지 → **CodeGraph MCP**로 진입점·호출 관계·영향 범위 분석 → 필요 시 소스·테스트 보조 확인  
> **참고**: 기존 `docs/PROJECT_AUDIT.md`(2026-07-14)는 구버전 이슈 기록. 본 문서는 **2026-07-20 전면 재감사**입니다.  
> **수정 반영 (2026-07-20)**: 아래 High/Medium 다수 항목을 코드에 반영했습니다. 회귀 테스트 **121 passed**.

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 CrossPoint e-ink 기기를 위한 뉴스 수집 → EPUB 빌드 → 무선 전송 GUI/CLI 툴입니다. 모듈 분리(SOLID), 프로세스/스레드 락, config 원자적 저장, 기기별 이력 DB, OPDS·웹 대시보드 인증, 최근 추가된 **클라우드 백업 동기화(`websync/backup`)** 까지 갖춘 성숙도 높은 데스크톱 앱입니다.

- **전체 위험도**: **Medium** (개인 로컬 사용 가정; LAN 공개·멀티 PC 동기화 사용 시 **Medium–High**)
- **핵심 문제 (우선순위 순)**:
  1. **설정 메모리 스냅샷 vs 디스크 경합** — GUI/`service.config`가 인메모리 dict를 잡고 저장하는 동안 백업 pull·다른 경로가 `config.json`을 갱신하면 **사이트 병합 결과가 덮어씌워질 수 있음** (High).
  2. **Windows 스케줄러 `cd /d` 경로 미인용** — 프로젝트 경로에 공백이 있으면 일간 스케줄 등록·실행이 깨질 수 있음 (High, 사용자 환경 의존).
  3. **레거시 `device_ip='*'` 이력이 모든 기기에 “전송 완료”로 취급** — 다중 기기 도입 전 DB를 마이그레이션한 사용자는 기기 추가 후에도 해당 URL 재전송이 막힐 수 있음 (High, 데이터 의존).
  4. **프리뷰·웹 대시보드 동기화의 TOCTOU** — 락 검사와 실제 실행 사이 레이스로 중복 스크래핑/이중 기동 가능 (Medium).
  5. **`BackupSyncService.push`의 `auto_export` 가드 미구현** — 서비스 래퍼에서는 막지만 직접 호출·미래 경로에서 옵션이 무시될 수 있음 (Medium).
  6. **문서 드리프트** — `CLAUDE.md`/`README`가 스크래퍼 수·`backup` 패키지·설정 스키마를 일부 반영하지 않음 (Medium, 유지보수 리스크).

이전 감사(2026-07-14)의 **OPDS 전체 메모리 로드**, **EPUB `set_identifier` 누락**, **`_last_pipeline_result` 클래스 변수**, **Watch 스레드 무한 누적** 등은 현재 코드에서 **해결 또는 상당 부분 완화**된 상태입니다.

---

## 2. Project Understanding

### 2.1 목적 (README / CLAUDE)

| 항목 | 내용 |
|------|------|
| 목적 | Xteink X3 뉴스·콘텐츠 수집 → e-ink용 EPUB → 무선 전송 자동화 |
| 핵심 가치 | 증분 동기화(SQLite), 다중 사이트/기기, Calibre·OPDS·웹 대시보드·스케줄 |
| 원칙 | SOLID, 모듈 단일 책임, 타입 힌트 |
| 진입 | `python x3_websync.py` (GUI) / `--sync` (스케줄·백그라운드) |

### 2.2 패키지 구조 (현재 코드 기준)

```
x3_websync.py                 # CLI/GUI, 단일 인스턴스 락
websync/
  core/                       # paths, process_lock, logger, article
  config/                     # manager, validator, exceptions
  db/                         # SyncHistoryDb
  scrapers/                   # 11종 + factory (css/rss/naver/…/soonsal/moneyletter)
  epub/                       # builder, css, cover, sanitize, themes
  upload/                     # uploader, device_client, host, remote_path
  pipeline/                   # SyncService 파사드 + sync/preview/selected
  backup/                     # 클라우드 포터블 JSON pull/push (신규)
  integrations/               # Calibre, ToastNotifier
  scheduler/                  # schtasks / launchd / crontab
  servers/                    # OPDS + dashboard/
  watch/                      # CalibreWatcher
  gui/                        # app_core, sync_tab, device_files, settings_tab(+backup_sync)
```

### 2.3 주요 실행 흐름 (CodeGraph)

```
main()
  ├─ [GUI] acquire_instance_lock()
  ├─ ConfigManager() → SyncService(config_manager)
  │     ├─ SyncHistoryDb
  │     └─ BackupSyncService
  ├─ [--sync]
  │     run_sync_pipeline()
  │       ├─ _pipeline_lock + ProcessFileLock (비차단)
  │       ├─ maybe_backup_pull()  → sites/history JSON 병합
  │       ├─ run_sync_pipeline_locked()
  │       │     scrape → needs_sync → translate/summarize → build → upload → mark_synced
  │       └─ maybe_backup_push()
  └─ [GUI] SyncAppGui
        ├─ 시작 시 백그라운드 maybe_backup_pull
        ├─ 탭: 동기화 / Calibre / 이력 / 기기 파일 / 고급 설정
        └─ Watch 큐 워커 / OPDS / 웹 대시보드
```

### 2.4 동시성·데이터 계층

| 계층 | 메커니즘 |
|------|----------|
| GUI 단일 실행 | Windows named mutex + 락 파일 / Unix flock |
| 파이프라인 | `SyncService._pipeline_lock` + `ProcessFileLock` |
| Config | `ConfigManager._lock` + tmp/bak/replace 원자 저장 |
| DB | `SyncHistoryDb._db_lock` + `sqlite3` timeout=10s |
| 업로드 | `ThreadPoolExecutor` (기기 병렬, max 4) |
| 백업 폴더 | 스레드 Lock + 폴더 내 `.backup_sync.lock` |
| Watch | 단일 워커 큐 + 락 acquire **timeout=30s** |

### 2.5 테스트 현황

- **117** tests collected (`pytest --collect-only`)
- 커버 양호: config load/save, db, uploader 일부, backup 단위, dashboard 일부, scheduler, process_lock
- CodeGraph 기준 **미커버/취약**: 전체 `run_sync_pipeline_locked` 통합, GUI 설정 저장 레이스, Watch 업로드, export/import_sites, dashboard handler 세부 경로

---

## 3. High-Risk Issues

### 3.1 인메모리 `service.config`와 디스크 config 경합 (설정 유실·사이트 롤백)

* **위치**: `websync/pipeline/service.py` (`self.config`), `websync/gui/app_core/helpers.py` (`_safe_save_config`), `websync/backup/service.py` (`pull` → `save_config`), GUI 사이트/설정 저장 경로
* **문제**:  
  - 런타임 설정 소스는 **`service.config`에 붙인 dict**이며, GUI는 이를 수정한 뒤 `save_config`로 디스크에 씁니다.  
  - 클라우드 **backup pull**은 디스크를 읽어 사이트를 병합·저장한 뒤 `service._reload_config()`로 갱신합니다.  
  - 그러나 GUI 스레드가 pull **이전**에 복사해 둔 오래된 `service.config` 참조를 이후 `_safe_save_config`하면, **방금 병합된 사이트 목록을 예전 내용으로 덮어쓸 수 있습니다.**  
  - `ConfigManager` 파일 락은 “동시 write의 원자성”만 보장하고, **read-modify-write 의미론적 병합은 없음**.
* **영향**: OneDrive 동기화·시작 시 pull과 사이트 편집/autosave가 겹치면 원격에서 가져온 사이트가 사라지거나, 반대로 로컬 편집이 유실될 수 있음.
* **근거**:  
  - `BackupSyncService._pull_unlocked`가 `config["sites"]=merged` 후 `save_config`  
  - GUI `_safe_save_config(config)`가 인자 dict를 그대로 저장 (`reload` 옵션이 있어도 호출 전 스냅샷이 오래되면 무의미)  
  - 사이트 토글/삭제가 `config = self.service.config` 후 인플레이스 수정
* **권장 수정 방향**:  
  1. 저장 시 **디스크 최신 load → UI/의도 필드만 패치 → save** (또는 버전/`updated_at` CAS).  
  2. 백업 pull 중 GUI 저장 차단 또는 직렬화 큐.  
  3. `service.config`를 “캐시”로만 쓰고 쓰기 API를 단일 진입점으로 통일.
* **우선순위**: **High**

---

### 3.2 Windows 일간 스케줄: 프로젝트 경로 공백 시 실패 가능

* **위치**: `websync/scheduler/manager.py` — `_register_windows`
* **문제**:  
  ```text
  cmd.exe /c "cd /d {self.project_dir} && \"{pythonw}\" \"{script}\" --sync"
  ```  
  `project_dir` 자체에 따옴표가 없어 경로에 공백·`&` 등이 있으면 `cd`/`cmd` 파싱이 깨집니다.
* **영향**: 스케줄러에 등록은 되어도 아침 동기화가 실행되지 않음 (로그/작업 스케줄러 기록에 실패). 사용자 홈 경로 `C:\Users\First Last\...` 등에서 흔함.
* **근거**: `_register_windows`의 `cmd_target` 문자열 조립 (CodeGraph 확인). Linux 쪽은 `shlex.quote` 사용.
* **권장 수정 방향**: `project_dir`/`python`/`script` 전부 적절히 인용 (`\"%s\"` 또는 `subprocess` 리스트 + schtasks 권장 형식). 등록 후 즉시 dry-run 검증.
* **우선순위**: **High**

---

### 3.3 레거시 `device_ip='*'` → 모든 기기에 동기화 완료로 간주

* **위치**: `websync/db/history.py` — `is_synced_for_device`, `_migrate_legacy_schema`, `LEGACY_DEVICE_IP`
* **문제**:  
  ```sql
  WHERE url = ? AND (device_ip = ? OR device_ip = ?)
  ```  
  두 번째 비교 대상이 `*`. 레거시 1-기기 DB 마이그레이션 행이 있으면 **이후 추가한 모든 기기도 해당 URL에 대해 전송 불필요로 처리**됩니다.
* **영향**: 다중 기기 도입 후 “이 기기만 안 받음” 재시도가 동작하지 않음. `needs_sync`/`pending_device_ips` 모두 영향.
* **근거**: `is_synced_for_device` 쿼리 및 마이그레이션 시 전 행 `device_ip='*'` 삽입.
* **권장 수정 방향**:  
  - `*`는 “알 수 없는 과거 기기 1대”로만 취급하고, **등록된 실제 IP와 매칭될 때만** 완료로 보거나  
  - 마이그레이션 후 첫 기기 IP로 재기록, `*` 행은 더 이상 “모든 기기 완료”로 확장하지 않기  
  - 설정/이력 UI에서 레거시 행 정리 도구 제공
* **우선순위**: **High** (레거시 DB 보유 사용자에게 한해; 신규 DB만 쓰면 영향 낮음)

---

### 3.4 `preview_articles` 락 미획득 — 파이프라인과 경쟁

* **위치**: `websync/pipeline/preview.py` — `preview_articles`
* **문제**: `is_pipeline_running()` 검사만 하고 `_pipeline_lock`/`ProcessFileLock`을 **획득하지 않음**. 검사 직후 다른 스레드/프로세스가 파이프라인을 시작하면 스크래핑·DB 조회가 겹칩니다.
* **영향**: 동일 사이트 이중 HTTP 부하, 프리뷰/동기화 로그 혼선, (드묾) DB 락 경합. 프리뷰는 업로드하지 않으므로 데이터 손상 위험은 제한적.
* **근거**: CodeGraph — preview는 lock acquire 호출 없음; sync는 acquire 후 실행.
* **권장 수정 방향**: 프리뷰도 동일 락을 non-blocking 또는 짧은 timeout으로 획득. 실패 시 현재처럼 빈 결과 + 메시지.
* **우선순위**: **Medium**

---

### 3.5 웹 대시보드 `/api/sync` busy 검사와 기동 사이 TOCTOU

* **위치**: `websync/servers/dashboard/handler.py` — `do_POST` `/api/sync`
* **문제**:  
  1. `pipeline_busy_callback()` True면 거절  
  2. 아니면 `threading.Thread(target=sync_cb).start()`  
  실제 `run_sync_pipeline` 락 획득은 스레드 안에서 일어남. 연타·다중 클라이언트 시 **여러 스레드가 거의 동시에 기동** → 대부분 한쪽만 락 성공·나머지는 “이미 실행 중”이지만, 불필요한 스레드/로그 노이즈 발생.
* **영향**: 기능 치명도는 낮음(내부 락이 최종 방어). 그러나 API 응답은 “시작됨”을 먼저 돌려줄 수 있어 UX 혼동.
* **근거**: handler 146–157행 근처 패턴.
* **권장 수정 방향**: sync 시작 API에서 락 try-acquire를 콜백이 동기적으로 시도하거나, “accepted/rejected”를 락 결과로 반환.
* **우선순위**: **Medium**

---

### 3.6 `BackupSyncService._push_unlocked`의 `auto_export` 미적용

* **위치**: `websync/backup/service.py` — `_push_unlocked` 약 239–242행
* **문제**:  
  ```python
  if not force and not bs.get("auto_export", True):
      pass  # no-op — 이후 그대로 파일 기록
  ```  
  옵션이 False여도 push가 계속됩니다. `SyncService.maybe_backup_push`가 사전 차단해 **현재 주 경로 피해는 제한적**.
* **영향**: 직접 `backup_sync.push()` 호출, 향후 CLI/테스트/리팩터 시 “자동 내보내기 끔”이 무시됨.
* **근거**: 위 dead branch; `maybe_backup_push`는 `auto_export`를 검사.
* **권장 수정 방향**: `skipped=True`로 early return. 단위 테스트 추가.
* **우선순위**: **Medium**

---

### 3.7 설정 검증이 경고만 — 잘못된 사이트도 실행 경로 진입

* **위치**: `websync/config/validator.py` — `log_validation_warnings`; `ConfigManager.load_config`
* **문제**: `validate_config` 오류가 있어도 로드·저장·스크래핑이 진행됩니다. URL 스킴 오류, limit 범위, 알 수 없는 type 등.
* **영향**: 사용자는 “동기화했는데 왜 비었지?”만 보고, 원인은 로그만. 잘못된 type은 `ScraperFactory`에서 예외.
* **근거**: `log_validation_warnings` docstring — “로드는 중단하지 않음”.
* **권장 수정 방향**: GUI 저장 시 blocking 검증(저장 거부), 파이프라인 시작 시 치명 오류 사이트 스킵 + 요약 토스트.
* **우선순위**: **Medium**

---

### 3.8 클라우드 백업: PC 간 폴더 락 실효성·OneDrive 충돌 파일

* **위치**: `websync/backup/service.py` — `_acquire_folder_lock` (`ProcessFileLock` on cloud folder)
* **문제**: 락 파일은 **같은 OS 로컬 프로세스 간**에만 의미 있습니다. 두 PC가 OneDrive 폴더를 동시에 push하면 클라우드 쪽에서 `sites (1).json` 충돌본이 생기거나 last-writer-wins로 덮일 수 있습니다. 앱은 충돌 파일명을 읽지 않습니다.
* **영향**: 멀티 PC 동시 사용 시 사이트 LWW/이력 합집합이 의도대로 안 맞을 수 있음.
* **근거**: `ProcessFileLock` 구현(로컬 flock/msvcrt); OneDrive는 별도 동기화 엔진.
* **권장 수정 방향**:  
  - 문서에 “한쪽 PC만 켜 두기 / 동기화 완료 후 사용” 명시 (USER_GUIDE 일부 있음)  
  - `exported_at`+기계 ID 기반 충돌 감지, `*.conflict` 보존  
  - push 전 remote mtime/exported_at 재확인
* **우선순위**: **Medium** (멀티 PC 실사용 시)

---

### 3.9 민감 정보: `config.json` 평문 API 키·토큰

* **위치**: `websync/config/manager.py` DEFAULT / 사용자 `config.json`; AI·OPDS·웹 대시보드
* **문제**: OpenAI API 키, 대시보드 토큰, OPDS 키가 평문 저장. 백업 동기화는 의도적으로 제외하지만 **로컬 config·백업 복사·화면 공유** 시 유출 가능.
* **영향**: 개인 PC 전용이면 수용 가능. 공유 PC·동기화 폴더에 **실수로 config 전체 복사** 시 위험.
* **근거**: README 보안 절; `_ensure_api_token` 자동 생성 후 파일 저장.
* **권장 수정 방향**: OS 키링(optional), export 시 마스킹 강화, GUI “시크릿 표시” 기본 숨김 유지.
* **우선순위**: **Medium** (위협 모델: 로컬 개인 → Low–Medium)

---

### 3.10 OPDS LAN: 쿼리 스트링 `api_key` 허용

* **위치**: `websync/servers/opds.py` — `_check_auth`
* **문제**: Bearer/`X-Api-Key` 외에 `?api_key=` 지원. 서버/프록시 액세스 로그에 키 유출 가능. 코드 주석도 “비권장” 명시.
* **영향**: LAN 공개 + 공용 로그 환경에서 키 노출.
* **권장 수정 방향**: 쿼리 인증 deprecated 제거 또는 설정 플래그로 기본 off.
* **우선순위**: **Low–Medium**

---

### 3.11 Windows Toast: PowerShell `-Command` + 인자 바인딩 한계

* **위치**: `websync/integrations/notifier.py` — `_show_windows`
* **문제**: 스크립트는 `$args[n]`을 쓰도록 개선되었으나, `powershell -Command script title text icon` 형태에서 **인자 전달 방식**이 환경에 따라 `$args`에 기대한 값이 안 들어갈 수 있음(인코딩/파싱). 제목·본문에 특수문자가 많으면 알림 실패(기능 비치명).
* **영향**: 알림만 실패, 동기화 자체는 진행.
* **권장 수정 방향**: `-File` 임시 스크립트 또는 `-EncodedCommand`, 실패 시 로그 폴백만 유지.
* **우선순위**: **Low**

---

### 3.12 `history.mark_synced` 반복 호출 시 row 단위 커밋

* **위치**: `websync/db/history.py` — `mark_synced`; `sync_pipeline` 루프
* **문제**: 기사×기기마다 연결·INSERT·commit. 대량 전송 시 디스크 I/O·락 시간 증가.
* **영향**: 성능·`database is locked` 확률 소폭 상승 (timeout 10s로 완화).
* **권장 수정 방향**: `mark_synced_many` 배치 API.
* **우선순위**: **Low**

---

### 이미 해결·완화된 항목 (이전 감사 대비)

| 이전 이슈 | 현재 상태 |
|-----------|-----------|
| OPDS 파일 전체 `read()` | 64KB 청크 스트리밍 |
| EPUB `set_identifier` 누락 | `build`/`build_digest` 모두 설정 |
| build vs digest CSS 불일치 | 둘 다 인라인 `<style>` + `_resolve_css` |
| `_last_pipeline_result` 클래스 변수 | 인스턴스 속성 |
| Watch 스레드 무한 생성 | 단일 워커 큐 |
| Watch 무한 blocking | `timeout=30.0` 후 스킵 |
| 사이트 import 후 메모리 config 미갱신 | `_reload_config` + tree refresh |

---

## 4. Potential Functional Gaps

*(확실하지 않은 항목은 **추정** 표기)*

| 항목 | 설명 | 구분 |
|------|------|------|
| 사이트 pull 후 GUI 편집 중 다이얼로그 | 트리만 refresh하고 열린 편집 창은 stale 가능 | **추정** (코드상 다이얼로그 독립) |
| `import_sites` URL만 중복 키 | 동일 소스 다른 셀렉터/이름이면 스킵 → 의도일 수 있음 | 기능 한계 |
| 이력 JSON 크기 상한 없음 | 수만 건 push 시 OneDrive·메모리 부담 | **추정** (규모 의존) |
| 백업에 EPUB/output 미포함 | 설계상 의도(설정+이력만). “백업” 기대와 불일치 가능 | 제품 갭 |
| 실시간 OneDrive 변경 watch 없음 | 시작/파이프라인/수동 sync만 — 설계 범위 | 문서화됨 |
| `validate`가 backup_sync.folder 존재 여부 미검사 | 잘못된 경로면 push 시 생성 시도·실패 | 소갭 |
| 스크래퍼 SSRF 가드 없음 | 사용자 설정 URL로 임의 HTTP — 데스크톱 단일 사용자 전제 | **추정** 위협 낮음 |
| HTML sanitize: `onclick`/svg 미제거 | e-ink 뷰어 특성상 실해 낮음 | Low |
| Calibre CLI 파싱/경로 | 테스트 거의 없음 — 버전별 깨짐 가능 | **추정** |
| `summary_html` in `build()` | AI 요약은 escape됨. 다른 경로 주입 시 XSS성 이슈 가능 | **추정** |
| 웹 대시보드 CSRF | SameSite=Strict로 완화. 커스텀 클라이언트는 토큰 필요 | Low |
| README “9종 스크래퍼” | 실제 factory **11종** (+ soonsal, moneyletter) | 문서 불일치 |
| CLAUDE.md 트리에 `backup/` 없음 | 구현·README 3b와 불일치 | 문서 불일치 |
| CLAUDE `config_version: 2` 스키마에 `backup_sync` 없음 | 코드 DEFAULT에는 존재, 버전 번호 없이 키 머지 | 문서 갭 |
| `docs/PROJECT_AUDIT.md` vs 루트 | 구감사와 병존 시 혼동 | 문서 운영 |

---

## 5. Recommended Fix Plan

### 1단계 — 즉시 수정 (기능 오동작·데이터 유실 방지)

1. **Config RMW 경합 해소**  
   - 저장 단일 API: disk load → merge patch → save  
   - backup pull과 GUI save 직렬화  
2. **Windows 스케줄러 경로 인용 수정** + 공백 경로 수동 검증  
3. **레거시 `device_ip='*'` 의미 축소** 또는 마이그레이션/정리 도구  
4. **`BackupSyncService.push`의 `auto_export` early-return** 수정  

### 2단계 — 안정성 개선

5. `preview_articles` 파이프라인 락 공유  
6. 웹 `/api/sync` 락 결과 기반 응답  
7. 설정 검증: GUI 저장 차단 + 파이프라인 사이트 스킵 요약  
8. 백업: push 전 remote `exported_at` 재확인, 충돌 파일 감지 로그  
9. `mark_synced` 배치화  

### 3단계 — 구조·문서·보안 정리

10. `service.config` 캐시 정책 문서화 또는 immutable 스냅샷  
11. OPDS 쿼리 `api_key` 제거/옵션화  
12. `CLAUDE.md` / `README.md` 동기화 (스크래퍼 목록, `websync/backup`, `backup_sync` 스키마, settings_tab)  
13. `docs/PROJECT_AUDIT.md`에 “최신본은 루트 `PROJECT_AUDIT.md`” 안내 또는 통합  
14. (선택) 시크릿 OS 키링, 이력 JSON 크기 경고  

---

## 6. Test Recommendations

### 6.1 반드시 추가

| 테스트 | 내용 |
|--------|------|
| `test_config_rmw_race` | 스레드 A: GUI식 stale dict save / 스레드 B: backup pull merge — **최종 sites가 유실되지 않음**을 고정 (수정 후 통과 기준) |
| `test_scheduler_windows_path_quoting` | 공백 포함 fake `project_dir`로 `_register_windows`가 만드는 `/tr` 문자열 검증 (subprocess mock) |
| `test_legacy_star_device_ip` | `device_ip='*'` 행이 있을 때 새 IP에 대해 `needs_sync`/`pending_device_ips` 기대 동작 명시 (정책 결정 후) |
| `test_backup_push_respects_auto_export` | `auto_export=False`, `force=False` → 파일 미작성 |
| `test_preview_respects_pipeline_lock` | 락 점유 중 preview → 빈 결과/스킵 |

### 6.2 보강 권장

| 테스트 | 내용 |
|--------|------|
| `run_sync_pipeline` 통합 (mock scraper/upload) | pull→filter→mark→push 훅 호출 여부 |
| dashboard `/api/sync` 연타 | 동시 POST 시 내부 락과 응답 일관성 |
| `import_sites` / `export_sites` | 포맷 오류, URL 중복, 원자성 |
| `export_all_posts` + 대량 `import_posts_union` | 성능 스모크·트랜잭션 일관성 |
| OPDS download path traversal | `../` 파일명 거부 (기존 realpath 검사 회귀) |
| Watch 큐 | 락 timeout 시 스킵 로그, 워커 종료 sentinel |

### 6.3 테스트 인프라

- GUI/tk 테스트는 선택; **비즈니스 로직은 service/backup/db/scheduler에 고정**하는 현재 방향 유지가 효율적.  
- Windows 전용 스케줄러 문자열 테스트는 `@pytest.mark.skipif` 없이 **순수 문자열 단언**으로 크로스플랫폼 유지.

---

## 부록 A. 문서 vs 구현 불일치 요약

| 문서 | 구현 | 비고 |
|------|------|------|
| README “스크래퍼 9종” / 모듈 “9종” | factory 11 키 | soonsal, moneyletter 추가됨 |
| CLAUDE 트리 `settings_tab`: epub/servers/watch/ai | + `backup_sync.py` | 누락 |
| CLAUDE에 `websync/backup` 없음 | 패키지 존재 | 누락 |
| CLAUDE config 예시 `backup_sync` 없음 | DEFAULT_CONFIG에 존재 | 누락 |
| CLAUDE “docs/PROJECT_AUDIT.md” | 본 파일은 루트 `PROJECT_AUDIT.md` | 이중 문서 |
| USER_GUIDE 클라우드 백업 | 구현과 대체로 일치 | 양호 |
| 이전 docs 감사: Watch 무한 blocking | timeout 30s + 큐 | 구식 |

---

## 부록 B. 감사 범위 밖 / 의도적 제한

- 네트워크 스크래퍼 사이트 구조 변경(네이버 등) — 운영 이슈  
- CrossPoint 펌웨어 버그  
- PyInstaller 배포 파이프라인 전체  
- 법적/저작권 크롤링 정책  

---

*이 문서는 코드를 수정하지 않는 감사 산출물입니다. 수정 착수 시 1단계 항목부터 적용하고, 회귀 테스트(§6)를 함께 추가하는 것을 권장합니다.*
