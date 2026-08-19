# Project Audit

> **감사 일자**: 2026-08-19  
> **감사 관점**: 기능 구현 안정성 (예외·검증·상태/데이터 흐름·동시성·경로/인코딩/OS·DB/설정·보안·테스트·문서-구현 정합성)  
> **분석 방법**: `README.md` / `CLAUDE.md` / `docs/DEVELOPER.md` 정독 → **CodeGraph MCP**로 엔트리포인트·호출 그래프·blast radius 분석 → 필요 구간에만 소스 대조 및 `pytest --collect-only` (253 collected)  
> **범위 밖 (초안)**: 코드 수정 없음. 스타일·네이밍 지적은 제외. 추정은 명시.  
> **개선 반영 (2026-08-19)**: 아래 권장 1~3단계(H1–H10, 취소 API, Watch `on_moved`, YouTube 1.x 호환, 문서 정합)를 코드·테스트에 반영함.

---

## 1. Executive Summary

Xteink X3 WebSync는 CrossPoint 펌웨어 X3 e-ink 기기를 위한 **수집 → EPUB → 무선 전송** 데스크톱 앱이다. 파이프라인 파사드(`SyncService`), 설정 CAS(`ConfigManager`), 기기별 이력(`SyncHistoryDb`), Ed25519 업데이터, OPDS/웹 대시보드가 역할별로 분리되어 있고, GUI/`--sync` 간 `ProcessFileLock` 직렬화도 실제 코드에 존재한다.

이전 루트 `PROJECT_AUDIT.md`(2026-08-16)는 업데이터 중심이었고 “전체 위험도 Very Low, 개선 과제 전부 반영”으로 닫혀 있었다. 이번 감사는 **기능 구현 전반**을 다시 봤고, 즉시 장애를 내는 Critical 원격 취약점은 없었다. 당시 High 항목(번역 스위치, Watch Tk 스레드, `--smoke` 스텁)과 권장 1~3단계는 **2026-08-19에 코드·테스트·문서에 반영**했다.

| 영역 | 평가 | 요약 |
|------|------|------|
| 핵심 파이프라인 (수집·중복제거·업로드·이력) | 양호 | 락·부분 전송·DB 오류 중단·기기 0대 거부가 구현되어 있음 |
| 설정/DB 무결성 | 양호 | 원자적 저장, revision CAS, SQLite WAL, 레거시 `*` 이관 |
| 업데이터 보안 | 양호 | Ed25519 + SHA-256 + HTTPS 강제 + 롤백. `--smoke`는 핵심 모듈 import 검증 |
| OPDS/대시보드 인증 | 양호 (전제 있음) | LAN 시 키 필수, Bearer 비교는 `compare_digest`. LAN HTTP 평문은 문서화된 전제 |
| GUI 비동기 | 양호 | Watch 감지 로그는 `root.after`, `_log_message`에 `TclError` 가드 |
| 스크래퍼 입력 검증 | 양호 | `fetch_url` http(s)+16MB, 파이프라인은 잘못된 스킴 스킵 |
| 문서 정합성 | 양호 | CustomTkinter·취소·스모크·락 경로를 USER_GUIDE/DEVELOPER/CLAUDE에 반영 |
| **전체 위험도 (반영 후)** | **Low** | High 항목과 권장 1~3단계 반영. 잔여는 §4 추정(G1~G6) 수준 |

**반영 완료 (2026-08-19)**

1. `Translator.is_available_for_site`가 전역 `enabled`를 먼저 본다  
2. Calibre Watch 감지 로그는 Tk 메인 스레드(`root.after`)로 전달  
3. `--smoke`가 `SMOKE_MODULES`를 실제로 import 하고 실패 시 종료 코드 1

---

## 2. Project Understanding

### 2.1 목적 (README / CLAUDE.md)

- 지정 뉴스·블로그·뉴스레터(13종 스크래퍼)를 모아 e-ink용 EPUB으로 빌드하고 X3에 무선 전송  
- SQLite로 기기별 중복 제거 (증분 동기화)  
- Calibre 서재·기기 파일·스케줄·공유 데이터 폴더·OPDS/웹 대시보드·Ed25519 자동 업데이트

개발 원칙: SOLID, 모듈 단일 책임, 타입 힌트.

### 2.2 실행 흐름 (CodeGraph + 진입점)

```
x3_websync.main()
  ├── --smoke          → run_smoke_check() (핵심 모듈 import, 실패 시 1)
  ├── --version        → 패키지 버전
  ├── --check-update   → UpdateService.check_for_update()
  ├── --apply-update   → apply_staged_update (헬퍼 프로세스, 서명/해시 재검증)
  ├── --sync           → GUI 락 없이 SyncService.run_sync_pipeline()
  └── [GUI]            → acquire_instance_lock() → SyncAppGui.run()
                           │
                           └─ SyncService (blast radius: GUI/대시보드/테스트 등 27+ 호출)
                                ├─ maybe_backup_pull → run_sync_pipeline_locked → maybe_backup_push
                                ├─ preview_articles / sync_selected_articles  (동일 파이프라인 락)
                                └─ begin_sync_pipeline_async  (대시보드 POST /api/sync → 202/409)
```

파이프라인 본문 (`websync/pipeline/sync_pipeline.py`):

1. config 리로드 → 활성 사이트 / 전송 기기 확인 (`no_sites` / `no_targets`)  
2. 레거시 `device_ip='*'` → 첫 대상 이력 키로 이관  
3. 사이트별 `ScraperFactory.get_scraper(type).fetch_articles`  
4. `article_sync_key` → `needs_sync(..., history_mode, key_aliases)`  
5. (선택) 번역 / AI 요약  
6. `per_site` 또는 `daily_digest` EPUB → `upload_to_targets(only_ips=pending)`  
7. 성공 IP만 `mark_synced_many`  
8. `_last_pipeline_result` + 토스트

### 2.3 핵심 모듈과 영향 범위 (CodeGraph)

| 심볼 | 역할 | Blast radius |
|------|------|----------------|
| `SyncService` (`pipeline/service.py`) | 락·백업 훅·파이프라인 파사드 | GUI `app_core`, 대시보드, 테스트 4종 이상 |
| `run_sync_pipeline_locked` | 실제 수집·빌드·전송 | `SyncService`만 호출 |
| `ConfigManager.update_config` | RMW + revision bump | backup pull/push, local_import |
| `SyncHistoryDb.needs_sync` / `mark_synced` | 기기별 중복 제거 | preview, sync_pipeline, backup |
| `X3Uploader.upload_to_targets` | 병렬 HTTP 업로드 (최대 4워커) | 파이프라인, Calibre 탭, Watch, 직접 업로드 |
| `ProcessFileLock` | 프로세스 간 파이프라인 직렬화 | temp 디렉터리의 고정 파일명 |

### 2.4 문서와 코드가 일치하는 부분

- GUI 락과 `--sync` 프로세스 락 분리 (`x3_websync.py`, `SyncService._try_acquire_pipeline_locks`)  
- 웹 대시보드 `begin_sync_pipeline_async` 계약 (202 수락 / 409 거부)  
- OPDS `normcase` + `realpath`로 경로 탈출 차단  
- 설정 결손 키 보강, `portable_data` ↔ `backup_sync` 미러  
- 스크래퍼 타입 SSOT는 `websync/scrapers/types.py`의 `SCRAPER_TYPES` (13종)

---

## 3. High-Risk Issues

각 항목은 현재 소스에 근거가 있다. 추정은 §4로 분리했다.

### H1. 번역 전역 스위치가 googletrans에서 무시됨

* 위치: `websync/pipeline/translator.py` — `Translator.is_available_for_site`  
* 문제: `provider == "googletrans"`이면 `self.enabled`를 보지 않고 패키지 로드 가능 여부만 본다. 기본 provider는 `"googletrans"`이고 기본 `enabled`는 `False`다. 파이프라인은 `is_available()`가 아니라 `is_available_for_site()`만 호출한다 (`sync_pipeline.py` 145행, `selected_sync.py` 83행).  
* 영향: 사이트에 `translate_to`만 켜져 있고 고급 설정의 번역이 꺼져 있어도, `googletrans`가 설치되어 있으면 본문이 외부 번역 API로 나간다. README는 “AI 요약·번역을 켜면 외부 전송”이라고 했는데, **끈 상태에서도 전송**될 수 있다.  
* 근거:

```27:35:websync/pipeline/translator.py
    def is_available_for_site(self, translate_to: str) -> bool:
        if not (translate_to or "").strip():
            return False
        if self.provider == "libretranslate":
            return self.enabled
        if self.provider == "googletrans":
            return self._get_gtrans() is not None
        return self.enabled
```

`libretranslate`만 `enabled`를 본다. 기존 `tests/test_translator.py`는 `enabled=False` + googletrans 조합을 검증하지 않는다.  
* 권장 수정 방향: 모든 provider에서 `self.enabled`를 먼저 검사. 사이트 `translate_to`는 그 다음 조건.  
* 우선순위: **High**

---

### H2. Calibre Watch가 Tk 메인 스레드 밖에서 위젯을 건드림

* 위치: `websync/gui/settings_tab/watch.py` — `on_new_file`; `websync/watch/calibre.py` — `_flush_pending`  
* 문제: Watchdog/`threading.Timer`에서 `on_new_file`이 호출되고, 그 안에서 `self.app._log_message(...)`를 직접 호출한다. `_log_message`는 `bottom_bar.log_txt`에 insert한다. 업로드 워커는 `root.after(0, ...)`를 쓰지만, **감지 로그는 after가 없다**.  
* 영향: 감시 중 로그 갱신 시 `RuntimeError: main thread is not in main loop` 또는 Tcl 크래시. 감시는 켜져 있는데 UI만 죽는 형태가 될 수 있다.  
* 근거:

```56:58:websync/gui/settings_tab/watch.py
            def on_new_file(fpath: str):
                self.app._log_message(f"👁 새 파일 감지: {os.path.basename(fpath)} → 전송 큐 대기 중")
                watch_queue.put(fpath)
```

```47:68:websync/gui/app_core/helpers.py
    def _log_message(self, message: str):
        self.bottom_bar.log_txt.configure(state="normal")
        self.bottom_bar.log_txt.insert(tk.END, message + "\n")
        ...
```

선택자 마법사(`selector_wizard.py`)는 `TclError`/`winfo_exists`를 쓰는데 Watch는 그렇지 않다.  
* 권장 수정 방향: `on_new_file`도 `root.after(0, ...)`로 로그. `_log_message` 진입부에 `winfo_exists` + `TclError` 가드.  
* 우선순위: **High**

---

### H3. `--smoke`가 문서·업데이터 계약과 다름

* 위치: `x3_websync.py` — `main()` smoke 분기; `websync/core/update_installer.py` — `apply_staged_update`  
* 문제: CLI 도움말과 설치기는 “바이너리 및 핵심 모듈 로드 무결성 스모크”라고 한다. 구현은 버전 문자열을 찍고 `exit(0)`만 한다.  
* 영향: PyInstaller 교체 후 `--smoke`가 0을 반환해도 **번들 누락·import 실패를 검출하지 못한다**. import는 파일 최상단에서 이미 일어나므로, 완전히 기동 불가한 exe는 걸러지지만 “기동만 되고 핵심 모듈이 빠진” 빌드는 통과한다. 롤백 트리거가 약해진다.  
* 근거:

```271:274:x3_websync.py
    if args.smoke:
        print(f"Xteink X3 WebSync v{__version__} smoke check OK")
        sys.exit(0)
```

`tests/test_updater_cli.py`도 stdout에 `"smoke check OK"`가 있는지만 본다.  
* 권장 수정 방향: smoke 경로에서 `ConfigManager`, `SyncService`, `ScraperFactory`, `EpubBuilder` 등 핵심 import/인스턴스를 실제로 수행하고 실패 시 non-zero. GUI(`SyncAppGui`)는 디스플레이 없는 헬퍼에서 깨질 수 있으니 제외하거나 지연 import.  
* 우선순위: **High** (업데이트 안전망)

---

### H4. 사이트 URL 검증이 파이프라인을 막지 않음

* 위치: `websync/config/validator.py` — `validate_site`, `log_validation_warnings`; `websync/scrapers/base.py` — `fetch_url`; `websync/pipeline/sync_pipeline.py`  
* 문제: URL은 `http://`/`https://`가 아니면 경고만 남긴다. `fetch_url`은 스킴·본문 크기·리다이렉트 대상을 제한하지 않는다. 선택자 도우미만 `is_private_or_local_url`로 사설망을 경고한다.  
* 영향: 잘못된 스킴·거대 응답·의도치 않은 내부 호스트 요청이 동기화 때 그대로 실행된다. 공유 폴더 `sites.json`이 병합되면(§4 G3) 다른 PC에서도 같은 URL을 친다.  
* 근거: `log_validation_warnings`는 “로드는 중단하지 않음”이 명시되어 있다. `fetch_url`은 `_session.get(url, ...)`만 수행. 파이프라인은 `validate_config` 결과를 보지 않는다.  
* 권장 수정 방향: 동기화 시작 시 활성 사이트 URL을 http(s)만 허용하고 실패 사이트는 스킵/집계. `fetch_url`에 최대 본문 크기(예: 8–16MB)와 리다이렉트 횟수 상한.  
* 우선순위: **Medium**

---

### H5. Calibre Watch가 `on_created`만 구독

* 위치: `websync/watch/calibre.py` — `_Handler.on_created`  
* 문제: `on_moved` / `on_modified`가 없다. Calibre와 많은 Windows 프로그램은 temp에 쓴 뒤 rename/move 한다.  
* 영향: “새 책 추가 시 자동 전송”이 조용히 안 되거나, 불완전 파일을 안정성 검사에서 스킵한다. 사용자는 감시가 켜져 있는데 전송이 없다고 느낀다.  
* 근거: 핸들러에 `on_created`만 정의. 안정성 검사(`_is_file_stable`)는 created 경로에만 적용.  
* 권장 수정 방향: `on_moved`의 dest 경로도 같은 확장자 필터 + debounce. dest가 감시 폴더 밖이면 무시.  
* 우선순위: **Medium**

---

### H6. 공유 폴더 락 실패 시 pull/push를 건너뛰고 동기화를 계속함

* 위치: `websync/backup/service.py` — `_acquire_folder_lock`, `_pull_unlocked`  
* 문제: 폴더 락은 **비차단**이다. 다른 PC/프로세스가 잡고 있으면 `skipped=True`만 하고 `SyncService._run_pipeline_body`는 로컬 캐시로 수집·이력을 기록한다.  
* 영향: OneDrive 양방향 사용 시 한쪽이 낡은 `sites.json`/`synced_posts.json` 기준으로 돌아가 중복 전송 또는 신규 누락이 난다. 락은 “정본 일치”를 보장하지 못하고 **최선 노력**이다.  
* 근거: `_acquire_folder_lock`이 `acquire(blocking=False)` 실패 시 즉시 return. `maybe_backup_pull`은 skipped여도 예외를 내지 않는다.  
* 권장 수정 방향: 짧은 재시도(예: 2초×5) 후 실패하면 로그를 에러 수준으로 올리고, 옵션으로 “정본 없으면 동기화 중단”.  
* 우선순위: **Medium**

---

### H7. EPUB 본문 정제가 `script`/`style`만 제거

* 위치: `websync/epub/sanitize.py` — `sanitize_body_html`  
* 문제: `iframe`, `object`, `embed`, `form`, `on*` 이벤트, `javascript:` 링크는 남는다.  
* 영향: 일부 리더/미리보기에서 스크립트성 마크업이 남거나, 이미지 포함 시 외부 리소스를 당긴다. e-ink CrossPoint에서는 위험이 낮지만 EPUB 산출물의 안전 계약은 약하다.  
* 근거: `find_all(["script", "style"])`만 decompose.  
* 권장 수정 방향: 위험 태그 화이트리스트(또는 블랙리스트 확장) + `onclick` 등 속성 제거.  
* 우선순위: **Low** (리더 크래시가 재현되면 Medium)

---

### H8. 뉴스레터 상세를 글마다 두 번 받음

* 위치: `websync/scrapers/newsletter_base.py` — `fetch_articles`, `_fetch_and_clean_detail`, `_get_title`  
* 문제: 본문용 GET 후 제목용으로 같은 URL을 다시 GET한다.  
* 영향: soonsal/moneyletter에서 글 수 × 2의 요청. 상대 서버 부하·타임아웃·부분 실패 증가. (같은 호의 `#story-N` 중복은 `urldefrag`로 최근 수정됨.)  
* 근거: `_fetch_and_clean_detail`과 `_get_title`이 각각 `fetch_url`을 호출.  
* 권장 수정 방향: 상세 응답 soup에서 `<title>`/`og:title`을 같이 추출.  
* 우선순위: **Low**

---

### H9. GUI 업로더가 `primary_device_id`를 넘기지 않음

* 위치: `websync/gui/app_core/helpers.py` — `_make_uploader`; 비교: `SyncService._apply_config_to_components`  
* 문제: 파이프라인 업로더는 `primary_device_id`를 넣어 `history_key`를 안정 id로 잡는다. GUI Watch/직접 업로드/Calibre 전송은 id 없이 IP만 쓴다.  
* 영향: Watch/Calibre 전송은 이력 DB에 안 남기므로 중복 키 문제는 당장 없다. 나중에 같은 업로더로 이력을 남기면 IP 변경 시 키가 갈라진다.  
* 근거: `_make_uploader` 생성자에 `primary_device_id` 인자 없음.  
* 권장 수정 방향: `_make_uploader`에 `primary_device_id=config.get("x3_primary_device_id")` 전달.  
* 우선순위: **Low**

---

### H10. 문서와 구현 불일치 (기능 오해로 이어지는 것)

* 위치: `CLAUDE.md`, `docs/DEVELOPER.md`, `README.md` vs 코드  
* 문제:

| 문서 | 코드 |
|------|------|
| CLAUDE.md GUI = `tkinter`+`ttk`, Clean Light 고정 | `websync/gui/widgets.py`는 **CustomTkinter**, System/Dark/Light |
| CLAUDE.md 테스트 246개 / DEVELOPER.md 196개(2026-07-27) | `pytest --collect-only` **253** |
| CLAUDE.md §5 로드맵 HIGH/MEDIUM이 “할 일”처럼 보임 | 로그·이력 탭·전용 스크래퍼·OPDS 등은 이미 구현. 문서 스스로도 “대부분 완료”라고 적어 두었으나 본문은 옛 할 일 목록 |
| `--smoke` = 모듈 로드 무결성 | 버전 출력만 |
| README 필수 패키지 설명에 CustomTkinter 미기재 | `requirements.txt`에 `customtkinter>=5.2.0` 필수 |

* 영향: 신규 기여자가 잘못된 스택/테스트 수/스모크 의미를 기준으로 작업한다.  
* 근거: 위 파일 대조 + collect-only 253.  
* 권장 수정 방향: CLAUDE/DEVELOPER의 테스트 수·GUI 스택·로드맵을 “현재 구현 / 남은 아이디어”로 분리.  
* 우선순위: **Medium** (동작 버그는 아니나 감사 범위에 포함)

---

### 잘 되어 있어 이번 목록에 넣지 않은 것

- `ConfigManager` 원자적 쓰기(`tmp`+`fsync`+`replace`)와 `_config_revision` CAS  
- `SyncHistoryDb` WAL + 스레드 락 + 레거시 스키마 이관  
- OPDS 다운로드 경로 `realpath`/`normcase`  
- 대시보드 Bearer/`compare_digest`, 세션 HMAC, `/api/sync` 409  
- 업데이터 HTTPS·서명·크기·만료·취소 이벤트  
- 업로드 파일명 한글 → short hash (CrossPoint 크래시 회피)  
- 스케줄러 hour/minute 정수 검증, `shell=False`

---

## 4. Potential Functional Gaps

확실하지 않은 항목은 **추정**으로 표시한다.

### 구현은 있으나 구멍이 보이는 보완점

| 항목 | 설명 | 구분 |
|------|------|------|
| 동기화 중 취소 | 파이프라인 락은 있으나 사용자 취소/타임아웃이 없다. 스크래핑이 길면 GUI가 “실행 중”에 고정된다. | 보완 |
| Watch 이력 미기록 | Calibre/Watch 전송은 `synced_posts`에 안 남는다. 같은 파일을 다시 쓰면 재전송된다. | 보완 (의도일 수 있음) |
| `fetch_url` 타임아웃 고정 | 사이트마다 15초. 큰 페이지·느린 블로그는 부분 실패. | 보완 |
| soonsal 제목 2회 GET | H8과 동일. 기능 오류는 아님. | 보완 |
| GUI `after(0)` TclError | `tab_calibre.py`, `preview.py`, `sync_control.py`, Watch 업로드 경로. 창을 닫은 뒤 콜백이 오면 예외. | 보완 |
| `X3Uploader.last_errors` | `ThreadPoolExecutor` 워커가 락 없이 dict를 쓴다. CPython GIL 아래 실무 영향은 작다. | 보완 |
| `ProcessFileLock` 경로 | `tempfile.gettempdir()/x3_websync_pipeline.lock` — **설치 폴더가 달라도 머신 전역 1개**. 두 휴대용 폴더를 동시에 `--sync`할 수 없다. | 보완 (의도일 수 있음) |
| 폰트 `Malgun Gothic` | `widgets.py`. Windows 전제. macOS/Linux는 대체 폰트에 의존. | OS 호환 |
| `epub_theme` 경로 | 화이트리스트는 validator 경고뿐. 수동 `config.json`에 `../`를 넣으면 `themes_dir()` 밖으로 읽기를 시도한다. | 입력 검증 |

### 추정

| ID | 내용 | 왜 추정인가 |
|----|------|-------------|
| **G1** | `youtube-transcript-api` 1.x에서 `YouTubeTranscriptApi.get_transcript`가 바뀌어 자막 수집이 전량 실패할 수 있다. `requirements-optional.txt`는 `>=0.6.0`. | 이 환경에서 1.x 실호출을 재현하지 않음 |
| **G2** | Calibre가 메타데이터만 갱신하면 `on_created`가 안 떠 Watch가 침묵한다. | 실제 Calibre 버전별 I/O 패턴 미실측 |
| **G3** | 공유 `sites.json`을 누군가 변조하면 피해자 PC가 임의 URL을 스크래핑한다. 폴더는 “사용자 신뢰” 전제. | 위협 모델이 로컬/동기화 폴더 신뢰에 달려 있음 |
| **G4** | LibreTranslate/Ollama 호스트는 사용자 문자열 그대로 `urlopen`. `file://` 등. 공격자는 사실상 설정 소유자. | 로컬 앱 자기 SSRF |
| **G5** | 대시보드 LAN + `X-Forwarded-Proto: https` 위조 시 Secure 쿠키가 붙어 HTTP에서 세션이 안 붙을 수 있다. 기본은 localhost. | 리버스 프록시 없는 일반 사용에서는 희귀 |
| **G6** | 일간 합본 모드에서 사이트 하나 수집 실패(`site_errors`)면 합본 전체 `success=False`. 사용자는 “반은 모였는데 실패”로 느낄 수 있다. | UX 해석. 코드상 `digest_success and site_errors == 0`이 의도일 수 있음 |

---

## 5. Recommended Fix Plan

### 1단계 — 즉시 (오동작·크래시·업데이트 안전망)

1. **H1** `is_available_for_site`에 `enabled` 가드. 회귀 테스트: `enabled=False` + `provider=googletrans` + `translate_to="ko"` → 번역 호출 0회.  
2. **H2** Watch `on_new_file` 로그를 `root.after`로 옮기고, `_log_message`에 위젯 생존 가드.  
3. **H3** `--smoke`가 핵심 모듈을 실제로 로드하게 하고, 설치기 스모크 실패 시 롤백 테스트를 유지한 채 CLI 테스트를 강화.

### 2단계 — 안정성

1. **H4** 파이프라인 진입 시 활성 사이트 URL 스킴 강제, `fetch_url` 본문 크기 상한.  
2. **H5** Watch `on_moved` 지원 + 확장자/폴더 필터.  
3. **H6** 백업 폴더 락 재시도. 정본 pull 실패를 로그/토스트에 명확히.  
4. GUI `after` 콜백 전반에 `TclError` 가드 (Calibre 탭, 프리뷰, 동기화 종료).  
5. 뉴스레터 상세 1회 GET으로 본문+제목 (H8).

### 3단계 — 구조·문서

1. **H10** CLAUDE.md / DEVELOPER.md / README: CustomTkinter, 테스트 253, 로드맵 “완료/잔여” 분리, smoke 의미 정정.  
2. EPUB sanitize 범위 확대 (H7).  
3. `_make_uploader`에 `primary_device_id` 전달 (H9).  
4. (선택) 프로세스 락을 `PROJECT_ROOT` 기준으로 바꿔 휴대용 다중 설치를 허용할지 결정.  
5. 동기화 취소 API (GUI 버튼 + 대시보드).  
6. YouTube 자막 API 1.x 호환 래퍼 (G1 확인 후).

---

## 6. Test Recommendations

현재 스위트는 config/DB/파이프라인/OPDS/대시보드/업데이터 단위가 두껍다. 아래는 **없는 계약** 위주다.

### 반드시 추가

| 테스트 | 실패 조건 (기대) |
|--------|------------------|
| `test_translator_googletrans_respects_enabled_false` | `enabled=False`이면 `_get_gtrans`/`translate`가 호출되지 않음 |
| `test_watch_on_new_file_logs_via_after` | `on_new_file`이 `_log_message`를 직접 호출하지 않음 (after 또는 큐만) |
| `test_cli_smoke_imports_core_modules` | `--smoke`가 0이어도, 구현 변경 후 핵심 import 실패 시 non-zero가 되도록 모듈 목록을 고정 |
| `test_pipeline_rejects_non_http_site_url` | `url=file:///tmp/x` 활성 사이트는 수집하지 않음 (H4 수정 후) |
| `test_calibre_watch_handles_moved_epub` | `on_moved` dest `.epub`이 debounce 큐에 들어감 |

### 보강

| 테스트 | 목적 |
|--------|------|
| `test_newsletter_extract_links_strips_fragment` | `newsletter_base` 공통 (soonsal 픽스처와 별도로 기반 클래스) |
| `test_newsletter_get_title_does_not_refetch` | 상세 1회 GET (H8 수정 후) |
| `test_backup_pull_retries_when_folder_locked` | 락 점유 중 skip vs retry |
| `test_fetch_url_enforces_max_bytes` | 거대 응답 절단/예외 |
| `test_sanitize_strips_iframe_and_events` | EPUB 정제 확대 후 |
| `test_make_uploader_passes_primary_device_id` | GUI 업로더 이력 키 정합 |
| `test_gui_after_callback_ignores_destroyed_widget` | 창 파괴 후 after 콜백 |

### 실사이트 (CI 제외)

- `scripts/validate_korean_scrapers.py --only soonsal,moneyletter,naver,tistory`  
- YouTube는 선택 의존성 + API 변경이 잦으므로 픽스처/모의 응답을 단위 테스트로 고정하고, 실호출은 수동.

### 허메틱 규칙 (유지)

`docs/DEVELOPER.md`대로 `config.json` / `sync_history.db` / `output/` / `logs/` 를 전제하지 말 것. 신규 테스트도 `tmp_path`만 사용.

---

## 부록. 이번 감사에서 확인한 최근 수정

작업 트리의 `newsletter_base._extract_links`는 `#story-N` fragment를 `urldefrag`로 제거한다. 순살 아카이브가 본문 1개 + 목차 앵커 5개를 올려 같은 호가 4회 이상 잡히던 문제는 **현재 코드 기준으로는 해소된 상태**다. 회귀는 `tests/test_soonsal_scraper.py`가 담당한다.
