# Project Audit

> **감사 일자**: 2026-07-14
> **감사 범위**: 기능 구현 관점 — 동시성, 예외 처리, 데이터 흐름, 보안, 파일/인코딩, 테스트 충실도
> **감사 방법**: CodeGraph MCP 기반 호출 관계 분석 + 소스 검수

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 9종 스크래퍼, EPUB 빌더, 다중 기기 무선 업로드, OPDS/웹 대시보드 서버, Calibre 연동, 스케줄러를 갖춘 다기능 데스크톱 애플리케이션입니다. 이전 감사(2026-07-13)에서 지적된 Calibre Watch 락 우회, 네이버 카페/포스트 인코딩, 커스텀 CSS 로깅 문제는 **모두 해결**된 상태입니다.

- **전체 위험도**: **Medium**
- **핵심 요약**:
  1. **Calibre Watch 무한 대기 및 락 점유** (High): Watch의 `upload_task`가 `blocking=True`로 파이프라인 락을 무한 대기하며, 대기 중에는 메인 동기화 파이프라인조차 시작할 수 없어 우선순위 역전이 발생합니다.
  2. **`preview_articles` 락 미획득** (Medium): 프리뷰가 `is_pipeline_running()` 검사만 하고 락을 획득하지 않아, 실행 중 config 리로드 및 DB 접근이 동시에 발생할 수 있습니다.
  3. **OPDS 대용량 파일 전체 메모리 로드** (Medium): 파일 다운로드 시 `f.read()`로 전체 파일을 메모리에 적재하여 대용량 EPUB 전송 시 메모리 부족 위험이 있습니다.
  4. **EPUB `build()` 식별자 누락 및 CSS 적용 방식 불일치** (Medium): `build()`에 `set_identifier`가 없어 EPUB 표준 위반이며, `build()`는 인라인 CSS, `build_digest()`는 외부 CSS 참조로 e-ink 리더기 호환성이 다릅니다.
  5. **`SyncService` 클래스 변수 공유** (Low-Medium): `_last_pipeline_result`가 클래스 변수로 선언되어 테스트 및 다중 인스턴스 시 상태 누수가 발생합니다.

---

## 2. Project Understanding

### 📋 프로젝트 목적
Xteink X3 (CrossPoint 펌웨어) e-ink 리더기를 위한 통합 뉴스 스크래핑 → EPUB 빌드 → 무선 전송 자동화 GUI 툴. SQLite 이력 DB로 증분 동기화를 지원하며, Calibre 서재 연동, OPDS 카탈로그 서버, 웹 대시보드 등 부가 기능을 포함합니다.

### 🏗️ 아키텍처 및 주요 실행 흐름

```
x3_websync.py (진입점)
  ├── --sync 모드: service.run_sync_pipeline() → sys.exit(0|1)
  └── GUI 모드: SyncAppGui(service).run()
                    ├── SyncTab (뉴스 동기화, 사이트 관리, 직접 전송)
                    ├── CalibreTab (서재 조회·전송)
                    ├── HistoryTab (이력 조회·삭제)
                    └── SettingsTab (OPDS/웹/Watch 서버, 테마, AI 설정)
```

**파이프라인 핵심 흐름** (`SyncService.run_sync_pipeline`):
1. `_pipeline_lock`(threading.Lock) + `_process_lock`(ProcessFileLock) 비차단 획득
2. config 리로드 → enabled_sites 필터링
3. 각 사이트별: ScraperFactory → fetch_articles → needs_sync 필터 → (번역/AI요약) → EpubBuilder.build → upload_to_targets
4. 성공 기기만 mark_synced (device_ip 단위)
5. daily_digest 모드 시 모든 기사를 하나의 EPUB으로 합본 빌드

**동시성 제어 계층**:
- **진입점**: GUI 단일 인스턴스 락 (Windows named mutex + 파일 락)
- **파이프라인**: `_pipeline_lock` (프로세스 내) + `_process_lock` (프로세스 간)
- **Config**: `ConfigManager._lock` (threading.Lock, 원자적 쓰기: tmp→bak→replace)
- **DB**: `SyncHistoryDb._db_lock` (threading.Lock) + `sqlite3.connect(timeout=10.0)`
- **업로드**: `ThreadPoolExecutor(max_workers=min(len, 4))` 병렬 전송

### 📊 테스트 현황
- 총 63개 테스트 (pytest) — pipeline, db, uploader, config, opds, web_dashboard, scrapers_errors, summarizer, scheduler, process_lock 등
- CodeGraph 분석 결과 다수의 핵심 메서드가 **테스트 미커버** 상태:
  - `preview_articles`, `sync_selected_articles` (⚠️ no covering tests)
  - `build_digest`, `_load_theme_css`, `_build_default_css` (⚠️ no covering tests)
  - `CalibreWatcher.start/stop`, `on_new_file`, `upload_task` (⚠️ no covering tests)
  - `CalibreManager.list_books`, `get_book_file_path` (⚠️ no covering tests)
  - `validate_config`, `log_validation_warnings` (⚠️ no covering tests)

---

## 3. High-Risk Issues

### 🔴 Calibre Watch `upload_task` 무한 blocking 대기 및 락 점유로 인한 우선순위 역전
* **위치**: `websync/gui/tab_settings.py` / `SettingsTab._toggle_watch` 내 `upload_task` 스레드
* **문제**: 새 파일 감지 시 `upload_task`가 `_pipeline_lock.acquire(blocking=True)`와 `_process_lock.acquire(blocking=True)`를 **타임아웃 없이 무한 대기**로 획득 시도합니다. 이전 감사의 "락 우회" 문제는 해결되었으나, 이번에는 반대로 **과도한 blocking**이 문제입니다.
* **영향**:
  1. 메인 뉴스 동기화(`run_sync_pipeline`)가 실행 중일 때 watch가 파일을 감지하면, `upload_task` 스레드가 `_pipeline_lock` 획득을 무한 대기합니다.
  2. 메인 파이프라인이 완료되어 락을 해제하면 watch가 즉시 락을 선점합니다. 이때 사용자가 GUI에서 "즉시 동기화"를 누르면 `run_sync_pipeline`의 non-blocking acquire가 실패하여 "이미 실행 중" 메시지가 표시됩니다. **watch의 단순 파일 전송이 뉴스 동기화보다 우선순위를 갖게 되는 역전 현상**이 발생합니다.
  3. 여러 파일이 연속으로 감시 폴더에 복사되면 각각 새 스레드가 생성되어 모두 락 대기 큐에 들어가며, 스레드가 무한히 누적될 수 있습니다.
* **근거**:
  ```python
  # websync/gui/tab_settings.py — _toggle_watch 내 on_new_file
  def upload_task():
      pipeline_acquired = False
      process_acquired = False
      try:
          # 타임아웃 없는 무한 blocking 대기
          pipeline_acquired = self.service._pipeline_lock.acquire(blocking=True)
          process_acquired = self.service._process_lock.acquire(blocking=True)
          # ...
      finally:
          if process_acquired:
              self.service._process_lock.release()
          if pipeline_acquired:
              self.service._pipeline_lock.release()
  threading.Thread(target=upload_task, daemon=True).start()
  ```
  `acquire(blocking=True)`에 `timeout` 인자가 없어 무한 대기하며, 파일 감지마다 새 스레드가 생성되어 락 대기 큐가 무한히 증가합니다.
* **권장 수정 방향**:
  1. `acquire(blocking=True, timeout=30.0)` 등 합리적 타임아웃 부여
  2. watch 전송 작업을 직렬 큐(`queue.Queue`)로 처리하여 스레드 누적 방지
  3. watch 전송은 파이프라인 락이 아닌 별도의 업로드 전용 뮤텍스를 사용하거나, `is_pipeline_running()` 시 전송을 연기/거부하는 정책 적용
* **우선순위**: **High**

---

### 🟡 `preview_articles`가 락을 획득하지 않고 config/db에 접근
* **위치**: `websync/pipeline/service.py` / `SyncService.preview_articles`
* **문제**: `preview_articles`는 `is_pipeline_running()` 검사만 수행하고 락을 획득하지 않습니다. 검사와 실제 실행 사이에 TOCTOU(Time-of-check to time-of-use) 경쟁이 존재하며, 프리뷰 실행 중 `_reload_config()`가 `self.config`를 교체하거나 DB를 읽는 동안 다른 스레드가 동시 접근할 수 있습니다.
* **영향**: 프리뷰 도중 스케줄러 `--sync`가 실행되거나 웹 대시보드에서 동기화가 트리거되면, config 객체 참조가 교체되는 도중에 stale 참조로 스크래퍼가 잘못된 설정을 사용할 수 있습니다. DB 읽기는 `_db_lock`으로 보호되지만, `self.config` 딕셔너리 참조 자체는 보호되지 않습니다.
* **근거**:
  ```python
  # websync/pipeline/service.py
  def preview_articles(self, ...):
      if self.is_pipeline_running():
          log("⚠️ 이미 파이프라인이 구동 중이므로 프리뷰를 실행할 수 없습니다.")
          return []
      # 락 획득 없이 config 리로드 및 DB 접근 수행
      self._reload_config()  # self.config 교체 발생
      # ... scraper.fetch_articles(site) 등 실행
  ```
  반면 `run_sync_pipeline`과 `sync_selected_articles`는 명시적으로 `_pipeline_lock`과 `_process_lock`을 획득합니다.
* **권장 수정 방향**:
  - 프리뷰 시작 시 읽기 전용 모드로 config 스냅샷을 만들어 사용하거나, `_pipeline_lock`을 읽기 모드로 획득(RLock 또는 별도 reader 락)하여 config 교체 중 일관성 보장
  - 최소한 `self.config = self.config_manager.load_config()` 대신 로컬 변수에 할당하여 사용: `config = self.config_manager.load_config()` 후 `config` 사용
* **우선순위**: **Medium**

---

### 🟡 OPDS 서버 대용량 파일 전체 메모리 로드
* **위치**: `websync/servers/opds.py` / `OPDSHandler._serve_file`
* **문제**: EPUB 파일 다운로드 시 `f.read()`로 전체 파일을 메모리에 한 번에 적재한 후 `wfile.write()`로 전송합니다.
* **영향**: EPUB 파일이 큰 경우(다량의 이미지 포함 시 50MB 이상) 서버 스레드의 메모리 사용량이 급증하며, 동시 다운로드 요청이 들어오면 메모리 부족으로 프로세스가 종료될 수 있습니다. e-ink 기기의 OPDS 클라이언트는 대용량 파일 다운로드 중 연결이 끊길 경우 재시도를 지원하지 않을 수 있습니다.
* **근거**:
  ```python
  # websync/servers/opds.py — _serve_file
  with open(fpath, "rb") as f:
      self.wfile.write(f.read())  # 전체 파일을 메모리에 로드
  ```
* **권장 수정 방향**:
  ```python
  CHUNK_SIZE = 64 * 1024  # 64KB
  with open(fpath, "rb") as f:
      while True:
          chunk = f.read(CHUNK_SIZE)
          if not chunk:
              break
          self.wfile.write(chunk)
  ```
  HTTP `Range` 요청 지원도 고려할 수 있으나, 최소한 청크 단위 전송은 필수적입니다.
* **우선순위**: **Medium**

---

### 🟡 EPUB `build()`의 `set_identifier` 누락 (EPUB 표준 위반)
* **위치**: `websync/epub/builder.py` / `EpubBuilder.build`
* **문제**: `build()` 메서드는 `set_title`과 `set_language`는 호출하지만, EPUB 표준에서 필수인 고유 식별자(`set_identifier`)를 설정하지 않습니다. 반면 `build_digest()`에서는 `book.set_identifier(f"x3-websync-digest-{today}")`를 호출합니다.
* **영향**: EPUB 검증기(epubcheck 등)에서 검증 실패가 발생하며, 일부 EPUB 리더기(특히 e-ink 기기)에서 메타데이터 누락으로 인해 도서가 정상적으로 인식되지 않거나 라이브러리에서 중복으로 표시될 수 있습니다.
* **근거**:
  ```python
  # websync/epub/builder.py — build()
  book = epub.EpubBook()
  book.set_title(f"{site_name} ({today_str})")
  book.set_language("ko")
  # set_identifier 호출 누락!

  # 반면 build_digest()에서는:
  book.set_identifier(f"x3-websync-digest-{today}")
  ```
* **권장 수정 방향**:
  ```python
  book.set_identifier(f"x3-websync-{safe_site_name}-{today_str}")
  ```
  사이트명+날짜 조합으로 고유 식별자 생성. 파일명 충돌 시간 접미사가 붙는 경우도 고려.
* **우선순위**: **Medium**

---

### 🟡 EPUB `build()` vs `build_digest()` CSS 적용 방식 불일치
* **위치**: `websync/epub/builder.py` / `build` 및 `build_digest`
* **문제**: `build()`는 `<style>` 태그로 CSS를 각 챕터에 인라인 삽입하지만, `build_digest()`는 `<link rel="stylesheet" href="style/default.css"/>`로 외부 CSS 파일을 참조합니다.
* **영향**: e-ink 리더기(X3 포함)의 EPUB 렌더링 엔진에 따라 외부 CSS 참조를 올바르게 처리하지 못할 수 있습니다. 두 빌드 경로가 다른 CSS 적용 방식을 사용하면 동일한 테마 설정이라도 시각적 결과가 달라질 수 있으며, e-ink 기기에서 합본 EPUB의 스타일이 깨질 수 있습니다.
* **근거**:
  ```python
  # build() — 인라인 CSS
  chapter.content = f"""
  ...
  <style>
      {custom_css}
  </style>
  ...
  """

  # build_digest() — 외부 CSS 참조
  ch.content = (
      ...
      f'<link rel="stylesheet" href="style/default.css" type="text/css"/>'
      ...
  )
  ```
* **권장 수정 방향**: 두 메서드 모두 동일한 방식(인라인 `<style>` 권장 — e-ink 호환성 최우선)을 사용하도록 통일. 또는 `build_digest()`에서도 각 챕터에 인라인 CSS를 삽입하도록 변경.
* **우선순위**: **Medium**

---

### 🟡 `SyncService._last_pipeline_result` 클래스 변수로 인한 상태 누수
* **위치**: `websync/pipeline/service.py` / `SyncService` 클래스 정의
* **문제**: `_pipeline_lock`, `_process_lock`, `_last_pipeline_result`가 모두 **클래스 변수**로 선언되어 모든 `SyncService` 인스턴스가 상태를 공유합니다.
* **영향**:
  1. 테스트 환경에서 여러 `SyncService` 인스턴스를 생성하면 `_last_pipeline_result`가 이전 테스트의 결과로 오염됩니다.
  2. `_pipeline_lock`과 `_process_lock`의 클래스 변수화는 의도된 동작(GUI와 --sync 간 직렬화)으로 보이지만, `_last_pipeline_result`는 인스턴스별로 독립되어야 하는 상태입니다.
  3. 웹 대시보드의 `get_status_callback`이 클래스 변수를 읽으므로, 동시 실행 시 잘못된 결과가 반환될 수 있습니다.
* **근거**:
  ```python
  class SyncService:
      _pipeline_lock = threading.Lock()        # 클래스 변수 (의도적)
      _last_pipeline_result: dict = {}          # 클래스 변수 (의도치 않은 공유)
      _process_lock = ProcessFileLock()         # 클래스 변수 (의도적)
  ```
* **권장 수정 방향**: `_last_pipeline_result`를 인스턴스 변수(`self._last_pipeline_result = {}`)로 변경. 락은 클래스 변수로 유지하되, `_last_pipeline_result`에 대한 접근 시 락 내에서 수행하도록 보강.
* **우선순위**: **Medium**

---

### 🟢 ToastNotifier Windows NotifyIcon 리소스 누수
* **위치**: `websync/integrations/notifier.py` / `ToastNotifier._show_windows`
* **문제**: PowerShell 스크립트에서 `System.Windows.Forms.NotifyIcon` 객체를 생성하고 `ShowBalloonTip`을 호출하지만, `Dispose()`를 호출하지 않습니다.
* **영향**: 알림이 표시될 때마다 시스템 트레이에 NotifyIcon 프로세스가 잔존할 수 있으며, 빈번한 알림 시 트레이 아이콘이 누적됩니다. PowerShell 프로세스가 종료되면 정리되지만, 알림 표시 후에도 백그라운드에서 PowerShell 프로세스가 일정 시간 유지될 수 있습니다.
* **근거**:
  ```python
  ps_script = (
      '... $obj = New-Object System.Windows.Forms.NotifyIcon; '
      '... $obj.ShowBalloonTip(5000);'
      # $obj.Dispose() 누락
  )
  ```
* **권장 수정 방향**: 스크립트 끝에 `Start-Sleep -Seconds 5; $obj.Dispose()` 추가.
* **우선순위**: **Low**

---

### 🟢 `sync_selected_articles`의 daily_digest 브랜치에서 `pending_ips` 중복 방지 로직 부재
* **위치**: `websync/pipeline/service.py` / `SyncService.sync_selected_articles` (daily_digest 분기)
* **문제**: `run_sync_pipeline`에서는 `pending_set`으로 IP 중복을 방지하지만, `sync_selected_articles`의 daily_digest 브랜치에서는 중복 체크 없이 `pending_ips.append(ip)`를 호출합니다.
* **영향**: `target_ips` 자체가 `_build_target_list()`에서 중복 제거된 리스트이므로 실제 중복은 발생하지 않습니다. 그러나 두 메서드 간 패턴 불일치로 인해 향후 `_build_target_list` 로직 변경 시 버그가 발생할 수 있습니다.
* **근거**:
  ```python
  # run_sync_pipeline (중복 방지 있음)
  pending_set = set()
  for ip in target_ips:
      if any(...):
          if ip not in pending_set:
              pending_set.add(ip)
              pending_ips.append(ip)

  # sync_selected_articles daily_digest (중복 방지 없음)
  pending_ips = []
  for ip in target_ips:
      if any(...):
          pending_ips.append(ip)  # 중복 체크 없음
  ```
* **권장 수정 방향**: `sync_selected_articles`의 daily_digest 브랜치에도 `pending_set` 패턴 적용하여 일관성 확보.
* **우선순위**: **Low**

---

### 🟢 `_open_output_folder`의 `os.sys.platform` 비관용적 접근
* **위치**: `websync/gui/tab_sync.py` / `SyncTab._open_output_folder`
* **문제**: `os.sys.platform`을 사용하는데, 이는 동작하긴 하지만 `sys.platform`의 비관용적 접근 방식입니다. 프로젝트 전체에서 `sys.platform`을 사용하는 다른 코드와 일관성이 없습니다.
* **영향**: 기능적 문제는 없으나, 정적 분석기(pyright)에서 경고를 발생시킬 수 있으며 유지보수성을 저해합니다.
* **근거**:
  ```python
  elif os.sys.platform == "darwin":  # sys.platform이 관용적
      import subprocess
      subprocess.Popen(["open", folder])
  ```
* **권장 수정 방향**: `import sys` 후 `sys.platform == "darwin"` 사용.
* **우선순위**: **Low**

---

## 4. Potential Functional Gaps

### 1. `sync_selected_articles`에서 번역(translate_to) 미적용 (추정)
- **내용**: `sync_selected_articles`는 AI 요약(`summarizer.is_available()`)은 적용하지만, 사이트별 `translate_to` 설정에 따른 번역은 적용하지 않습니다. `run_sync_pipeline`에서는 `translator.is_available_for_site(translate_to)` 체크 후 번역을 수행합니다.
- **보완 제안**: 선택 전송 시에도 번역 파이프라인을 적용하거나, 프리뷰 단계에서 번역 여부를 사용자에게 명시.

### 2. 웹 대시보드 `/api/sync`가 동기화 결과를 반환하지 않음 (추정)
- **내용**: 웹 대시보드에서 `POST /api/sync`는 `threading.Thread(target=sync_cb).start()`로 비동기 시작만 하고 즉시 200 응답을 반환합니다. 동기화 완료 여부는 `/api/status`를 폴링해야 확인할 수 있습니다.
- **보완 제안**: WebSocket 또는 Server-Sent Events(SSE)로 실시간 진행 상황을 푸시하거나, 최소한 `/api/sync` 응답에 작업 ID를 포함하여 추적 가능하도록 개선.

### 3. OPDS 서버 Range 요청 미지원 (추정)
- **내용**: OPDS `_serve_file`이 HTTP Range 헤더를 처리하지 않아, 대용량 EPUB 다운로드 중 일시 정지/재개가 불가능합니다.
- **보완 제안**: `Range`/`Content-Range` 헤더 처리 추가 (HTTP 206 Partial Content).

### 4. config.json 스키마에 `allow_lan` 기본값 명시 부재 (추정)
- **내용**: `DEFAULT_CONFIG`의 `opds_server`와 `web_dashboard`에 `allow_lan` 키가 있지만, 실제 config.json 샘플에는 없습니다. `load_config`의 deep merge가 기본값(false)을 보강하므로 기능적 문제는 없으나, 스키마 문서와 샘플 config.json 간 불일치가 존재합니다.
- **보완 제안**: `DEFAULT_CONFIG`의 스키마를 CLAUDE.md에 명시된 JSON 예시와 완전히 일치시키고, `config.json` 초기 생성 시 모든 키를 포함.

### 5. EPUB 빌더 예외 시 임시 파일 정리 부재 (추정)
- **내용**: `build()`에서 `epub.write_epub(file_path, book)` 호출 전 예외가 발생하면, `output_dir`에 빈 또는 불완전한 EPUB 파일이 남을 수 있습니다.
- **보완 제안**: `try/except`로 빌드 실패 시 부분 파일 삭제 처리 추가.

### 6. 스크래퍼 HTTP 요청 재시도 로직 부재 (추정)
- **내용**: 모든 스크래퍼가 `requests.get(url, timeout=15)`로 단일 요청만 수행하며, 일시적 네트워크 오류 시 재시도하지 않습니다.
- **보완 제안**: `requests.adapters.HTTPAdapter`로 재시도 정책(예: 3회, 백오프) 적용을 `BaseScraper` 또는 공통 유틸에 추가.

---

## 5. Recommended Fix Plan

### 1단계: 즉시 수정 (안정성 및 크래시 방지)

1. **Calibre Watch `upload_task` 타임아웃 및 큐잉**:
   - `acquire(blocking=True, timeout=30.0)` 적용, 타임아웃 시 로그 출력 후 스킵
   - 파일 감지 시 즉시 새 스레드 생성 대신 `queue.Queue`에 적재 후 단일 워커 스레드가 순차 처리하도록 변경
   - Watch 전송 중 메인 파이프라인이 시작되어야 하는 경우 Watch가 양보하도록 우선순위 정책 수립

2. **EPUB `build()` 식별자 추가**:
   - `book.set_identifier(f"x3-websync-{safe_site_name}-{today_str}")` 추가

3. **OPDS 파일 전송 청크화**:
   - `f.read()` → `CHUNK_SIZE` 단위 루프 전송으로 변경

### 2단계: 안정성 개선 (데이터 일관성 및 호환성)

1. **`preview_articles` config 스냅샷 사용**:
   - `config = self.config_manager.load_config()`을 로컬 변수에 할당하여 사용
   - 또는 `_pipeline_lock` 획득 후 config 리로드 수행

2. **EPUB CSS 적용 방식 통일**:
   - `build_digest()`를 `build()`와 동일한 인라인 `<style>` 방식으로 통일

3. **`_last_pipeline_result` 인스턴스 변수화**:
   - 클래스 변수 → `self._last_pipeline_result = {}` 인스턴스 변수로 변경

4. **ToastNotifier Dispose 추가**:
   - PowerShell 스크립트에 `Start-Sleep -Seconds 5; $obj.Dispose()` 추가

### 3단계: 구조 개선 (테스트 충실도 및 확장성)

1. **테스트 커버리지 확대**:
   - `preview_articles`, `sync_selected_articles` 단위 테스트 추가
   - `build_digest`, `_load_theme_css` 테스트 추가
   - `CalibreWatcher` start/stop/debounce 통합 테스트 추가
   - `validate_config`, `log_validation_warnings` 테스트 추가

2. **스크래퍼 공통 재시도 로직**:
   - `BaseScraper`에 `requests.Session` 기반 재시도 어댑터 추가

3. **`sync_selected_articles` 번역 적용**:
   - `translate_to` 설정에 따른 번역 파이프라인 통합

---

## 6. Test Recommendations

### 1. Calibre Watch 동시성 및 타임아웃 테스트
- **목적**: `upload_task`의 타임아웃 동작 및 락 대기 중 메인 파이프라인 시작 시나리오 검증
- **테스트 케이스**:
  - 파이프라인 실행 중 파일 감지 시 watch가 타임아웃 내 대기하는지
  - watch 락 점유 중 `run_sync_pipeline`이 정상적으로 "실행 중" 응답을 반환하는지
  - 연속 파일 감지 시 스레드가 무한히 증가하지 않는지 (큐잉 적용 후)

### 2. `preview_articles` 동시성 테스트
- **목적**: 프리뷰 실행 중 config 리로드가 발생할 때 stale 참조로 인한 오류 검증
- **테스트 케이스**:
  - 프리뷰 도중 `run_sync_pipeline`이 시작될 때 예외 없이 처리되는지
  - `_reload_config` 중 스크래퍼가 이전 config를 안전하게 사용하는지

### 3. EPUB 빌더 표준 준수 테스트
- **목적**: `build()`와 `build_digest()`의 EPUB 표준 준수 검증
- **테스트 케이스**:
  - `build()` 결과 EPUB에 identifier 메타데이터가 존재하는지 (수정 후)
  - 두 빌드 경로의 CSS가 동일하게 적용되는지 (수정 후)
  - 대용량 기사(100개 이상) 빌드 시 메모리/시간 안정성

### 4. OPDS 대용량 파일 전송 테스트
- **목적**: 청크 전송 적용 후 대용량 파일 다운로드 안정성 검증
- **테스트 케이스**:
  - 50MB 이상 EPUB 파일 다운로드 시 메모리 사용량이 일정한지
  - 동시 다운로드 요청(3개 이상) 시 메모리 부족 없이 처리되는지

### 5. `sync_selected_articles` 통합 테스트
- **목적**: 선택 전송 파이프라인의 DB 기록 및 부분 실패 처리 검증
- **테스트 케이스**:
  - daily_digest 모드에서 모든 기기 전송 성공 시 모든 URL이 mark_synced되는지
  - 부분 실패 시 성공 기기만 이력이 기록되는지
  - 이미 전송된 기기가 스킵되는지

### 6. Config 검증기 테스트
- **목적**: `validate_config`의 모든 검증 규칙 검증
- **테스트 케이스**:
  - 포트 범위 위반(1023, 65536) 시 에러 메시지
  - font_size 범위 위반(7, 49) 시 에러 메시지
  - epub_merge_mode 잘못된 값 시 에러 메시지
  - site type이 지원하지 않는 값일 때 에러 메시지
