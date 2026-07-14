# Project Audit

## 1. Executive Summary

본 감사 보고서는 **Xteink X3 WebSync Manager** 프로젝트의 기능 구현 상태, 비동기 동시성 제어, 스크래퍼 예외 처리, 설정 및 파일 처리 등 다각도의 코드 품질과 잠재적 위험 요소를 감사한 결과입니다.

- **전체 위험도**: **Medium**
- **핵심 요약**:
  1. **동시성 및 비동기 처리 이슈**: GUI 수동 동기화 및 백그라운드 웹 대시보드 API 간의 락 획득 실패 시, 사용자에게 시각적 알림이 미비하고 조용히 실패 처리가 될 가능성이 있습니다.
  2. **Calibre Watch의 전송 동시성**: 파일 감시로 작동되는 자동 업로드 기능이 서비스 파이프라인의 락(`_process_lock`, `_pipeline_lock`)을 획득하지 않고 별도 스레드에서 즉시 전송을 수행해 기기 측 동시 HTTP 요청 크래시가 발생할 수 있습니다.
  3. **인코딩 안정성**: 네이버 블로그 스크래퍼와 달리 신규 추가된 네이버 카페/포스트 스크래퍼에서는 `apparent_encoding` 미지정으로 인해 특정 한글 콘텐츠가 깨진 채 EPUB으로 빌드될 위험이 있습니다.
  4. **테마 CSS 폴백 로깅 미비**: 커스텀 CSS 파일을 불러오지 못했을 때 GUI 상에 실패 알림이 없고 자동 인라인 폴백만 이루어져 디버깅이 어렵습니다.

---

## 2. Project Understanding

**Xteink X3 WebSync Manager**는 e-ink 단말기(CrossPoint 펌웨어 기반)에 다중 사이트 뉴스 및 PC Calibre 서재 도서를 무선 전송해주는 통합 유틸리티입니다.

### 🏗️ 주요 아키텍처 및 흐름
- **동기화 엔진 (`SyncService`)**: `ScraperFactory`를 통한 다중 채널 크롤링, AI 요약(`Summarizer`), 번역(`Translator`)을 수행하고 `EpubBuilder`로 EPUB 문서를 만듭니다. 중복 전송 방지를 위해 `SyncHistoryDb`를 거쳐 `X3Uploader`가 무선으로 파일을 전송합니다.
- **GUI 컨트롤러 (`SyncAppGui`)**: Tkinter 기반의 탭형 매니저 툴로서, 역할별로 나뉜 4개의 탭(`SyncTab`, `CalibreTab`, `HistoryTab`, `SettingsTab`)과 하단 바(`BottomBar`)로 구성되어 비동기 스레드(`threading.Thread`)를 통해 백그라운드 작업을 실행합니다.

---

## 3. High-Risk Issues

### 🔴 Calibre Watch 자동 전송 시 파이프라인 락 우회
* **위치**: `websync/gui/tab_settings.py` / `SettingsTab._toggle_watch` 안의 `on_new_file` 및 `upload_task` 스레드
* **문제**: 감시 폴더 내에 새 파일이 감지되어 `on_new_file` 콜백이 호출될 때, 파이프라인의 메인 락인 `_pipeline_lock`이나 `_process_lock`을 확인하거나 획득하지 않고 즉시 별도 스레드를 생성하여 업로드(`upload_to_targets`)를 실행합니다.
* **영향**: 메인 뉴스 동기화 작업이 실행 중이거나 Calibre 서재 탭에서 대량의 도서 전송을 수행하는 도중에 감시 기능이 트리거되면, 단말기(X3)의 경량 웹 서버로 다중 업로드 HTTP 요청이 동시에 가해집니다. 이로 인해 전송이 실패하거나 단말기가 크래시될 수 있습니다.
* **근거**: 
  ```python
  # websync/gui/tab_settings.py
  def on_new_file(fpath: str):
      self.app._log_message(f"👁 새 파일 감지: {os.path.basename(fpath)} → 자동 전송 시작")
      def upload_task():
          results = self.app._make_uploader().upload_to_targets(fpath)
          # ...
      threading.Thread(target=upload_task, daemon=True).start()
  ```
  `upload_task` 내부에서 락을 점유하거나 대기하는 안전장치가 존재하지 않습니다.
* **권장 수정 방향**: `upload_task` 시작 전에 `self.service.is_pipeline_running()`을 체크하여 바쁠 경우 대기열(Queue)에 넣거나, `_pipeline_lock` 획득을 시도하도록 동기화 처리를 추가해야 합니다.
* **우선순위**: **High**

### 🟡 네이버 카페 및 포스트 스크래퍼의 인코딩 문제
* **위치**: `websync/scrapers/naver_cafe.py` (`_fetch_article_content`), `websync/scrapers/naver_post.py` (`_fetch_post_content`)
* **문제**: HTML 텍스트를 읽어 파싱할 때 `requests.get` 결과물에서 `resp.encoding`을 검증하거나 `apparent_encoding`으로 대입하지 않고 즉시 `resp.text`를 파싱합니다.
* **영향**: 대상 네이버 카페 또는 포스트 본문의 인코딩 사양이 UTF-8이 아닌 특정 EUC-KR 등의 변종 헤더로 전달될 경우, 한글이 깨진 깨진 문자가 수집되고 결국 깨진 EPUB 파일이 생성될 수 있습니다.
* **근거**: 
  ```python
  # websync/scrapers/naver_cafe.py
  resp = requests.get(content_url, headers=HEADERS, timeout=15)
  resp.raise_for_status()
  soup = BeautifulSoup(resp.text, "html.parser") # apparent_encoding 처리 누락
  ```
  기존 `naver.py`(블로그 스크래퍼)에서는 이 문제를 방지하기 위해 다음과 같이 구현되어 있습니다:
  ```python
  post_response.encoding = post_response.apparent_encoding
  post_soup = BeautifulSoup(post_response.text, "html.parser")
  ```
* **권장 수정 방향**: `naver_cafe.py`와 `naver_post.py`에서 개별 본문 및 목록을 패치할 때 `resp.encoding = resp.apparent_encoding` 구문을 파싱 전에 호출하도록 수정합니다.
* **우선순위**: **Medium**

### 🟡 커스텀 CSS 테마 경로 획득 실패 시 피드백 미비
* **위치**: `websync/epub/builder.py` / `EpubBuilder._load_theme_css`
* **문제**: 사용자가 지정한 `custom.css` 파일 경로에서 파일을 읽어오는 중 예외(파일 없음, 권한 오류 등)가 발생하면 그냥 조용히 `pass`하고 넘어가 결국 기본 인라인 CSS로 빌드됩니다.
* **영향**: 사용자는 GUI에서 커스텀 CSS 테마를 올바르게 지정했다고 생각하지만 실제로는 적용되지 않으며, 왜 적용되지 않는지 원인을 전혀 파악할 수 없습니다.
* **근거**:
  ```python
  # websync/epub/builder.py
  if self.epub_theme == "custom" and self.epub_custom_css:
      try:
          with open(self.epub_custom_css, "r", encoding="utf-8") as f:
              css_text = f.read()
      except Exception:
          pass # 예외 발생 시 에러 로깅이나 사용자 피드백이 누락됨
  ```
* **권장 수정 방향**: `except Exception as e:` 블록에서 로거를 통해 warning 로그를 작성하도록 변경하고, GUI에서도 오류 상태를 로그 텍스트창에 노출할 수 있는 구조를 마련해야 합니다.
* **우선순위**: **Medium**

### 🟢 LAN 공개 시 윈도우 방화벽 예외 문제
* **위치**: `websync/gui/tab_settings.py` / `SettingsTab` 내 OPDS 및 웹 서버 실행 영역
* **문제**: 사용자가 LAN 공개(0.0.0.0 바인딩) 옵션을 활성화하더라도 Windows 방화벽이 해당 포트(8765, 8766)의 외부 연결을 허용하지 않으면 단말기가 서버에 접속할 수 없습니다.
* **영향**: 사용자가 설정을 켰으나 전송 실패 등이 지속되어 네트워크 문제로 오인할 가능성이 있습니다.
* **근거**: 현재 서버 실행 코드 및 토글 메서드에서 OS 레벨의 방화벽 상태 안내나 포트 열기 가이드가 GUI 및 로그에 언급되지 않습니다.
* **권장 수정 방향**: LAN 공개 옵션을 활성화하고 서버를 구동할 때, 윈도우 환경인 경우 방화벽 예외 처리가 필요할 수 있다는 힌트성 문구(ToolTip 또는 HintLabel)를 SettingsTab UI에 배치합니다.
* **우선순위**: **Low**

---

## 4. Potential Functional Gaps

### 1. 선택적 동기화 실행 중 메인 락 제어 관련 알림 부족 (추정)
- **내용**: 프리뷰 대화상자에서 "선택 기사 기기로 전송"을 실행할 때, 이미 전체 동기화가 백그라운드(스케줄러 또는 웹 대시보드 API)에서 가동 중이라면 `sync_selected_articles` 메서드는 락 획득 실패로 조용히 `False`를 리턴합니다.
- **보완 제안**: 락을 획득하지 못해 중단되었을 경우 사용자에게 "현재 다른 동기화 작업이 실행 중입니다. 잠시 후 다시 시도해주세요."라는 메시지 박스를 띄워 인지시키는 흐름이 필요합니다.

### 2. 네이버 포스트 스크래퍼의 비공개/유료 포스트 필터링 누락 (추정)
- **내용**: `naver_post.py`에서 링크들을 수집하여 루프를 돌 때, 멤버 전용 혹은 유료 포스트 등으로 인해 비로그인 세션에서 접근 불가능한 글을 수집 시도할 경우 `_fetch_post_content`가 `None`을 반환하고 건너뜁니다.
- **보완 제안**: 스킵된 포스트 수에 대해 skipped 통계를 합산하고 로그에 명확히 표시하여, 사용자가 왜 몇몇 글이 빠졌는지 이해할 수 있도록 정보를 제공해야 합니다.

---

## 5. Recommended Fix Plan

### 1단계: 즉시 수정 (안정성 및 크래시 방지)
1. **Calibre Watch 업로드 동기화**:
   - `SettingsTab._toggle_watch` 내 `upload_task` 스레드 진입 시 `self.service.is_pipeline_running()` 혹은 락을 획득하도록 제어 구조 적용.
2. **네이버 카페/포스트 스크래퍼 인코딩 보정**:
   - `naver_cafe.py` 및 `naver_post.py` 본문 요청에 `apparent_encoding` 구문 추가.

### 2단계: 안정성 개선 (UX 피드백)
1. **테마 CSS 로딩 예외 로깅**:
   - `builder.py`에서 `custom.css` 로드 실패 예외에 대해 `logger.warning` 및 예외 메시지를 로그 창에 전달.
2. **락 획득 실패 시 GUI 팝업 알림**:
   - 프리뷰 및 선택 전송에서 락 획득 실패 시 `messagebox.showwarning`을 띄워 사용자 혼선 방지.

### 3단계: 구조 개선
1. **네트워크 가이드 추가**:
   - GUI 탭4의 LAN 공개 옵션 근처에 방화벽 예외 등록 안내 추가.

---

## 6. Test Recommendations

### 1. Calibre Watch 동시성 테스트 케이스 작성
- `watchdog` 이벤트가 뉴스 동기화 파이프라인 동작 도중에 동시에 발생할 때, 락을 대기하거나 거절하는 흐름이 테스트 단에서 예외 없이 제어되는지 모의(Mocking) 테스트 추가.

### 2. 비정상 인코딩 본문 수집에 대한 통합 테스트
- `naver_cafe.py` 와 `naver_post.py`를 테스트할 때 EUC-KR 및 UTF-8 외의 인코딩 웹 응답 모의 데이터를 넘겨주었을 때도 파싱 결과 깨짐 현상이 없는지 검증하는 테스트 구축.
