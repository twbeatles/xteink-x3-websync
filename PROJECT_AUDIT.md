# Project Audit

> **감사 일자**: 2026-08-03  
> **감사 초점**: CSS 선택자 도우미·`link_selector`·한국 블로그 휴리스틱 추가 이후 **기능 구현 안정성** 및 **Superpowers(TDD·계획 기반·에이전트 자동화 적합성)**  
> **방법**: `README.md` / `CLAUDE.md` 숙지 → **CodeGraph MCP**로 호출 관계·영향 범위 분석 → 필요 시 소스 정밀 확인·관련 pytest 실행  
> **범위 한정**: 신규 기능(`selector_assistant` / `selector_wizard` / `CssSelectorScraper` 확장)을 중심으로 하되, 파이프라인·설정·문서 정합성과의 접점도 포함  
> **이전 감사(2026-07-31)**: 한글 파일명 short hash, OPDS `normcase`, `flush_backup_push` 등은 **현재 코드에 반영된 상태**로 재확인함 (본 문서에서는 재현 이슈로 다루지 않음)  
> **개선 반영 (2026-08-03)**: 1~3단계 권장 수정 대부분 코드·테스트·문서에 반영. 상세는 아래 §8.

**관련 테스트 스냅샷 (감사 시점)**:  
`tests/test_selector_assistant.py` + `test_selector_assistant_kr.py` + sanitize/opds/flush 관련 **19 passed**

---

## 1. Executive Summary

**Xteink X3 WebSync Manager**는 e-ink 기기용 뉴스·블로그 수집 → EPUB → 무선 전송 도구이며, 이번 감사 대상인 **CSS 선택자 도우미**는 임의 URL에 대해 정적 HTML 기반 선택자 추천·검증·미리보기를 **추가 브라우저 의존성 없이** 제공한다. 순수 로직(`selector_assistant`)과 GUI(`selector_wizard` + `sites` 다이얼로그)로 분리된 설계는 방향이 올바르고, 오프라인 픽스처 단위 테스트도 갖춰져 있다.

다만 **기능적으로 실사용·배포·동시성에서 깨질 수 있는 결함**이 신규 경로에 집중되어 있다.

### 핵심 문제 (요약)

| # | 문제 | 우선순위 |
|---|------|----------|
| 1 | GUI 백그라운드 스레드가 종료된 다이얼로그에 `after` 콜백 / 위젯 갱신을 시도할 수 있음 (TclError·`_busy` 고착) | **High** |
| 2 | 워커 스레드에서 `self._html` / `self._analysis` 등 공유 상태를 직접 갱신 (Tk/데이터 race) | **High** |
| 3 | `analyze_page` + RSS path probe가 사용자 URL에 대해 다수 HTTP GET (지연·내부망 스캔 성격, SSRF 유사 표면) | **Medium** |
| 4 | 목록 본문 폴백이 아이템 전체 DOM을 허용 → 잘못된 선택자여도 “성공”처럼 보이며 저품질 EPUB 생성 가능 | **Medium** |
| 5 | EXE `hiddenimports`에 `selector_assistant` / `selector_wizard` 미등재 (추적 누락 시 frozen ImportError 위험) | **Medium** |
| 6 | `CLAUDE.md` 스키마·스크래퍼 목록이 `link_selector`·도우미 모듈을 반영하지 않음 (문서 드리프트) | **Low~Medium** |
| 7 | Superpowers 관점: GUI·통합 경로 무테스트, Red-Green 증적 없음, 에이전트가 안전하게 회귀시키기 어려운 층 | **Medium** (프로세스) |

- **전체 위험도 (신규 기능 기준)**: **Medium–High**  
  - 핵심 동기화 파이프라인 자체는 기존 락/이력 구조가 견고하나, **사이트 등록 UX 신규 경로**는 스레드 안전성·배포 누락·품질 폴백이 약하다.  
- **이전 High 이슈(한글 파일명 뭉개짐 등)**: short hash 도입으로 **완화 확인** — 본 감사의 잔존 Critical은 아님.

---

## 2. Project Understanding

### 2.1 목적 (README / CLAUDE)

- CrossPoint 펌웨어 X3 e-ink 기기에 **뉴스·블로그 EPUB 무선 전송**
- SQLite 기기별 중복 제거, 스케줄/`--sync`, Calibre·기기 파일·OPDS·웹 대시보드 등 부가 기능
- 개발 원칙: SOLID, 타입 힌트, 팩토리 기반 스크래퍼 확장

### 2.2 주요 실행 흐름 (CodeGraph + CLAUDE)

```
x3_websync.py
  ├─ GUI: SyncAppGui → SyncSitesMixin._open_site_dialog
  │         └─ SelectorWizardPanel
  │               ├─ analyze_page / discover_feeds(probe_paths) / suggest_selectors
  │               ├─ evaluate_selector (캐시 HTML)
  │               └─ CssSelectorScraper.fetch_articles (수집 미리보기)
  │
  └─ --sync / 전체·선택 동기화: SyncService
        ├─ ProcessFileLock + threading.Lock
        ├─ ScraperFactory → CssSelectorScraper (type=css, link_selector 포함)
        ├─ EpubBuilder → X3Uploader → SyncHistoryDb.mark_synced
        └─ BackupSyncService pull/push
```

### 2.3 신규 기능 모듈 역할

| 모듈 | 역할 | 테스트 |
|------|------|--------|
| `websync/scrapers/selector_assistant.py` | 페이지 분석, 피드 발견, 휴리스틱 추천, `build_recommended_site_config` | 단위·KR 픽스처 (있음) |
| `websync/gui/sync_tab/selector_wizard.py` | 분석/테스트/미리보기 UI, daemon 스레드 + `dialog.after` | **없음** |
| `websync/gui/sync_tab/sites.py` | 사이트 폼 + `link_selector` + 위자드 연결 | **없음** |
| `websync/scrapers/css.py` | `link_selector`, 제목/링크/목록 본문 폴백, 상세 본문 후보 | 단위 일부 |

### 2.4 설계상 강점

- GUI와 순수 분석 로직 분리 → pytest로 휴리스틱 회귀 가능
- RSS/전용 타입 우선 추천 → 한국 기술 블로그 실측과 정합
- 기존 필수 의존성만 사용 (브라우저 자동화 미도입)
- 파이프라인 본체는 프로세스 락으로 GUI/`--sync` 직렬화

---

## 3. High-Risk Issues

실제 코드 근거가 있는 문제만 기술한다. (이전 감사에서 **이미 수정된** 한글 파일명·OPDS·flush 이슈는 제외)

---

### [이슈 1] 다이얼로그 종료 후 `after` 콜백으로 TclError / `_busy` 고착 가능

* **위치**: `websync/gui/sync_tab/selector_wizard.py`  
  - `_on_analyze` → `work` → `self.dialog.after(0, lambda: self._apply_analysis(...))`  
  - `_on_test` / `_on_preview_scrape` 동일 패턴 (`_finish_test`, `_finish_preview`)
* **문제**:  
  분석·미리보기는 `threading.Thread(daemon=True)`로 실행되고, 완료 시 **모달 다이얼로그**에 `after`로 UI를 갱신한다.  
  사용자가 요청 진행 중 **취소/창 닫기**를 하면 위젯이 파괴된 뒤 콜백이 실행될 수 있다.  
  콜백 진입 시 `winfo_exists()` / `TclError` 가드가 없으며, 실패 시 `_busy = False`에 도달하지 못하면 **이후 분석 버튼이 영구 무시**될 수 있다 (`if self._busy: return`).
* **영향**:  
  사이트 등록 중 간헐적 크래시 또는 “페이지 분석이 더 이상 안 됨” UX. 재현은 네트워크 지연 시 창을 빨리 닫을 때 가능성이 높다.
* **근거**:  
  CodeGraph 호출 경로: `SelectorWizardPanel._on_analyze` → `analyze_page` → `dialog.after` → `_apply_analysis`.  
  `winfo_exists` 검색 결과 해당 파일에 보호 로직 없음.
* **권장 수정 방향**:  
  - `after` 콜백 최상단: `if not self.dialog.winfo_exists(): return`  
  - `try/except tk.TclError`로 위젯 갱신 보호  
  - `finally`에서 `_busy = False` 보장  
  - (선택) 요청 generation 카운터로 stale 응답 폐기
* **우선순위**: **High**

---

### [이슈 2] 워커 스레드에서 공유 상태 직접 기록 (데이터 race)

* **위치**: `selector_wizard.py` / `_on_test` 내부 `work()`  
  ```text
  self._html = analysis.html
  self._base_url = analysis.base_url
  self._analysis = analysis
  ```
  (메인 스레드가 아닌 백그라운드에서 할당)
* **문제**:  
  Tkinter 위젯뿐 아니라, 분석 캐시 필드를 워커가 직접 갱신한다. 동시에 메인 스레드가 DOM 클릭·추천 적용으로 `_analysis`를 읽으면 부분 갱신/교체 경쟁이 난다.  
  `_on_analyze`는 `after`로만 상태를 쓰는 반면, `_on_test` 경로는 일관성이 깨져 있다.
* **영향**:  
  드물게 잘못된 캐시 HTML로 선택자 테스트 결과가 섞이거나, 예외·불일치 UI. Tk 문서상 비메인 스레드 UI 접근 규칙과도 어긋나는 패턴.
* **근거**:  
  `_on_test`의 `work()` 본문 (CodeGraph/소스). `_apply_analysis`만 메인 스레드로 국한된 설계와 불일치.
* **권장 수정 방향**:  
  워커는 `(msg, analysis_or_none)`만 만들고, **모든 필드 할당은 `_finish_test` 등 메인 스레드 콜백에서만** 수행.
* **우선순위**: **High**

---

### [이슈 3] RSS path probe + 사용자 URL fetch — 지연 및 네트워크 표면 확대

* **위치**:  
  - `selector_assistant.analyze_page(..., probe_feeds=True)`  
  - `discover_feeds(..., probe_paths=True)` → origin + `/rss.xml`, `/feed`, … 최대 약 8회 `fetch_url`
* **문제**:  
  1) 페이지 1회 + 피드 프로브 N회 순차 GET → 느린 사이트에서 **분석 UI가 수십 초** 걸릴 수 있다.  
  2) 스킴은 http(s)로 제한되나, **사설 IP·localhost·메타데이터 주소** 차단은 없다. 데스크톱 앱·사용자 의도 URL이므로 전형적 서버 SSRF와는 다르지만, 오입력·악성 링크 시 **내부망 스캔성 요청**이 가능하다.  
  3) 수집 미리보기(`CssSelectorScraper`)도 동일 `fetch_url`로 상세 페이지를 limit만큼 추가 요청한다 — 파이프라인 락과 **무관**.
* **영향**:  
  UX 지연, 대상 사이트 rate limit, (드묾) 내부 호스트 오인 요청.
* **근거**:  
  `discover_feeds` path probe 루프; `analyze_page` 기본 `probe_feeds=True`; 위자드 미리보기는 `SyncService` 락 미사용.
* **권장 수정 방향**:  
  - 프로브 병렬화 또는 HEAD 우선·본문 길이 상한  
  - UI에 “피드 확인 중” 단계 표시, 타임아웃 총량 캡  
  - (선택) loopback/링크-로컬 경고 또는 차단 옵션  
  - 미리보기와 전체 동기화 동시 실행 시 안내
* **우선순위**: **Medium**

---

### [이슈 4] 목록 본문 폴백이 과도하게 관대함 — 잘못된 선택자의 침묵 성공

* **위치**: `websync/scrapers/css.py` / `_extract_list_content`  
  - `content_selector` 실패 시 `content_elem = post` (아이템 전체)  
  - 텍스트가 비어 있지 않으면 성공으로 간주
* **문제**:  
  본문 선택자가 틀려도 목록 카드 전체(날짜·태그·공유 UI 포함)가 EPUB 본문이 된다.  
  위자드 **수집 미리보기**도 동일 스크래퍼를 쓰므로, 사용자는 “미리보기 성공”으로 착각하고 저장할 수 있다.  
  상세 페이지 옵션이 꺼진 채 운영되면 저품질 전자책이 누적된다.
* **영향**:  
  e-ink 가독성 저하, “수집은 되는데 내용이 이상함” 류 지원 비용.
* **근거**:  
  `_extract_list_content` 폴백 분기; 미리보기 → `CssSelectorScraper.fetch_articles`.
* **권장 수정 방향**:  
  - 폴백 사용 시 `last_fetch_stats`에 `content_fallback=True` 기록 및 GUI 경고  
  - 미리보기 UI에 “본문 선택자 미매칭 → 목록 카드 전체 사용” 명시  
  - 설정 저장 시 `fetch_detail_page` 권장 토스트 (분석 메타와 연동)
* **우선순위**: **Medium**

---

### [이슈 5] PyInstaller `hiddenimports` 누락 위험 (frozen EXE)

* **위치**: `x3_websync.spec` `hiddenimports`  
  - `websync.scrapers.css` 등은 있으나 **`websync.scrapers.selector_assistant` 없음**  
  - **`websync.gui.sync_tab.selector_wizard` 없음**
* **문제**:  
  CLAUDE/DEVELOPER는 새 모듈을 `hiddenimports`에 넣도록 요구한다.  
  `sites.py`가 정적 import하므로 Analysis가 따라갈 **가능성은 높으나**, 과거 스크래퍼 누락 사례와 동일한 실패 모드를 방치하면 **EXE에서 사이트 추가 시 ImportError**가 날 수 있다.
* **영향**:  
  소스 실행은 정상, 배포 바이너리만 선택자 도우미/사이트 다이얼로그 실패.
* **근거**:  
  `x3_websync.spec` 목록 대조; `sites.py` → `SelectorWizardPanel` → `selector_assistant` 정적 import.
* **권장 수정 방향**:  
  hiddenimports에 두 모듈 명시 추가 + frozen 스모크(사이트 다이얼로그 open) 체크리스트.
* **우선순위**: **Medium**

---

### [이슈 6] CSS 선택자·빈 필드 검증 부재 (저장·설정 검증)

* **위치**:  
  - `sites.py` `save_site` — name/url/limit만 검사, **선택자 비어 있음 허용**  
  - `websync/config/validator.py` `validate_site` — type/url/limit만, **item/title/content/link_selector 미검증**
* **문제**:  
  `type=css`인데 `item_selector=""`로 저장 가능 → 동기화 시 `soup.select("")` 예외 또는 전량 실패.  
  잘못된 soupsieve 문법도 저장 단계에서 걸러지지 않는다.
* **영향**:  
  스케줄/`--sync`에서 사이트 단위 실패 로그, 사용자 인지 지연.
* **근거**:  
  `validate_site`가 limit 이후 즉시 return; GUI save 분기.
* **권장 수정 방향**:  
  - css 타입: 필수 선택자 비공백 + `evaluate_selector` 문법 체크(로컬 dummy soup)  
  - `log_validation_warnings`에 선택자 경고 포함
* **우선순위**: **Medium**

---

### [이슈 7] 문서 드리프트 — CLAUDE.md / README vs 구현

* **위치**:  
  - `CLAUDE.md` 파일 트리·설정 스키마 `sites[]` — **`link_selector` 없음**, `selector_assistant` / `selector_wizard` 미기재  
  - README 빠른 시작 — “추천 프리셋” 중심, **선택자 도우미·최적 설정 적용** 미언급  
  - `docs/USER_GUIDE.md` / `DEVELOPER.md`는 부분 반영됨
* **문제**:  
  에이전트·기여자가 CLAUDE만 보고 확장하면 스키마/모듈을 놓친다. Superpowers 계획 기반 개발에서 **단일 진실 소스 불일치**는 재작업 비용을 키운다.
* **영향**:  
  잘못된 패치, hiddenimports 누락 반복, 사용자 발견성 저하.
* **근거**:  
  `CLAUDE.md` sites 스키마 grep `link_selector` 0건; README 사이트 등록 절에 도우미 없음.
* **권장 수정 방향**:  
  CLAUDE 스키마·트리·스크래퍼 표 갱신; README 한 줄 링크(USER_GUIDE 선택자 도우미).
* **우선순위**: **Low** (기능 버그는 아니나 유지보수 **Medium** 효과)

---

### [이슈 8] `copy.copy`로 BS4 태그 복제 — 구현 취약성 (추정 강화: 잠재)

* **위치**: `css.py` `_extract_list_content` — `from copy import copy` 후 `content_elem = copy(content_elem)`
* **문제**:  
  BeautifulSoup 태그 shallow copy는 버전·파서에 따라 부모/문서 연결이 어색해 `select`/`decompose` 동작이 예상과 다를 수 있다.  
  현재 단위 테스트는 짧은 목록 요약 경로를 통과하나, **remove_selectors + 폴백** 조합의 엣지 케이스는 커버가 얇다.
* **영향**:  
  (추정) 특정 HTML에서 remove 미적용 또는 예외 → 스킵 증가.
* **근거**:  
  코드 경로 존재; 전용 테스트 부재. **확정 장애 리포트는 아님 → 추정 포함.**
* **권장 수정 방향**:  
  `copy.copy` 대신 `BeautifulSoup(str(elem), parser)` 재파싱 또는 `deepcopy` 정책 고정 + 픽스처 테스트.
* **우선순위**: **Low** (추정)

---

### [참고] 이전 High 이슈 상태 (재검증)

| 과거 이슈 | 현재 코드 | 상태 |
|-----------|-----------|------|
| 한글 파일명 `_` 뭉개짐 | `_sanitize_filename` + md5 short hash | **완화됨** |
| OPDS Windows 대소문자 | (기존 감사 반영·`test_opds_normcase`) | **완화됨** |
| 종료 시 백업 push 유실 | `flush_backup_push` + 테스트 | **완화됨** |

---

## 4. Potential Functional Gaps

확실하지 않은 항목은 **추정**으로 표시.

1. **선택자 도우미와 전체 동기화 락 비연동**  
   - 미리보기/분석은 파이프라인 락을 잡지 않음 → 동기화 중에도 대상 사이트에 추가 부하.  
   - **추정**: 의도적(빠른 UX)이나 명시 문서 없음.

2. **저장 전 “미리보기 성공” 강제 없음**  
   - 잘못된 CSS도 저장 가능. 도우미는 선택 사항.

3. **웹 대시보드에 동일 분석 API 없음**  
   - GUI 전용. 원격 설정 사용자는 수혜 없음. **기능 공백(의도 범위 밖일 수 있음).**

4. **SPA/JS 전용 사이트**  
   - 문서화는 되었으나, 자동으로 “수집 불가”를 저장 차단하지는 않음.

5. **`build_recommended_site_config`의 `title_selector="."` → `"a"` 치환**  
   - 아이템이 `<a>`인 경우 상대 `select_one("a")` 실패 가능 → 제목 폴백에 의존. 토스형 링크 목록에서 일부 스킵 관측됨(실측). **부분 갭.**

6. **import/export 사이트 JSON**  
   - `link_selector`는 필드 복사 시 포함될 수 있으나 export 스키마 문서화 부족. **추정: 동작은 dict 통째라 유지.**

7. **Superpowers 산출물 부재**  
   - 세션 plan은 있었으나 저장소 내 `spec.md`/`tasks.md` 형태의 기능 스펙이 없음 → 에이전트 재개 시 컨텍스트 손실. **프로세스 갭.**

8. **휴리스틱 과적합**  
   - 한국 기술 블로그·워드프레스에 튜닝됨. 해외 소형 블로그는 품질 저하 가능. **추정.**

---

## 5. Recommended Fix Plan

### 1단계 — 즉시 수정 (안정성·크래시)

1. `selector_wizard` 모든 `after` 콜백에 **위젯 생존 검사 + TclError 가드 + `_busy` finally 해제**
2. 워커 스레드의 `self._html`/`_analysis` 직접 할당 제거 → 메인 스레드만 상태 갱신
3. `x3_websync.spec`에 `selector_assistant`, `selector_wizard` **hiddenimports 추가**
4. (권장 동반) CSS 저장 시 빈 `item_selector` 거부

### 2단계 — 안정성·품질 개선

1. 목록 본문 폴백 시 stats/GUI 경고; 미리보기 문구 강화  
2. RSS probe 총 시간 상한·진행 표시·(선택) 사설 IP 경고  
3. `validate_site`에 css 선택자 문법/필수 필드  
4. `copy.copy` 본문 복제 방식을 명시적 재파싱으로 고정 + 테스트  
5. 수집 미리보기 시 파이프라인 실행 중이면 경고

### 3단계 — 구조·문서·에이전트 적합성

1. `CLAUDE.md` / README 스키마·모듈 트리 동기화  
2. `build_recommended_site_config` + `CssSelectorScraper` 계약 테스트 (아이템=`a` 패턴)  
3. 기능 스펙을 저장소 `docs/` 또는 Speckit 산출물로 고정 (Superpowers 재실행 가능)  
4. (선택) 웹 대시보드 분석 API는 별 로드맵

---

## 6. Test Recommendations

### 6.1 즉시 추가할 단위/통합 테스트

| 테스트 | 목적 |
|--------|------|
| `test_wizard_callback_ignores_destroyed_dialog` | mock dialog `winfo_exists=False` 시 콜백 no-op, `_busy` 해제 (로직을 콜백 헬퍼로 추출 후) |
| `test_worker_does_not_mutate_state` | 상태 갱신 함수가 메인 전용임을 계약 테스트 |
| `test_validate_site_css_requires_item_selector` | 빈 선택자 거부 |
| `test_list_content_fallback_flag` | 폴백 사용 시 stats/플래그 |
| `test_detail_fallback_candidates` | content_selector 오설정 + 상세 페이지에서 fallback 성공 |
| `test_anchor_item_title_link_contract` | item=`a[href*="…"]` + title/link 폴백으로 N건 수집 |
| `test_spec_hiddenimports_include_selector_modules` | `x3_websync.spec` 문자열에 모듈명 포함 (기존 spec 테스트 패턴 확장) |

### 6.2 Superpowers / TDD 관점 권고

| 원칙 | 현재 | 권고 |
|------|------|------|
| **Red-Green-Refactor** | 순수 로직 테스트는 사후 보강 형태. GUI는 무테스트 | 다음 버그픽스는 **실패 테스트 먼저** 커밋 가능한 형태로 |
| **계획 기반** | 세션 plan만 존재, 리포 고정 스펙 약함 | `docs/SELECTOR_ASSISTANT.md` 또는 Speckit `spec.md`에 수용 기준 명문화 |
| **환경 격리** | 네트워크 테스트 없음(양호), 실측은 수동 스크립트 | CI는 픽스처 only 유지; live probe는 `scripts/` + 수동 |
| **에이전트 자동화 적합성** | `selector_assistant`는 순수·고적합성; GUI는 Tk 결합으로 에이전트 검증 곤란 | UI 상태 머신을 순수 함수로 더 추출 (`apply_analysis_model` 등) |
| **검증 후 완료 주장** | 단위 19건 통과 확인됨 | frozen EXE 스모크·다이얼로그 스레드 시나리오는 아직 증거 없음 → **완료 선언 금지 영역** |

### 6.3 수동 체크리스트 (배포 전)

1. EXE 빌드 후 사이트 추가 → 페이지 분석 → 최적 설정 적용 → 저장  
2. 분석 중 다이얼로그 닫기 → 재오픈 후 분석 재실행  
3. 동기화 실행 중 수집 미리보기  
4. RSS 있는 기술 블로그 URL → type=rss 추천 확인  
5. CSS only 사이트 → fetch_detail ON 미리보기 본문 길이 확인  

---

## 7. Superpowers 적합성 종합 (요약)

| 영역 | 점수 (주관) | 코멘트 |
|------|-------------|--------|
| 도메인 순수 로직 분리 | 높음 | `selector_assistant` 분리는 에이전트·TDD에 유리 |
| 테스트 하네스 | 중상 | 오프라인 픽스처·KR 회귀 있음; GUI/스레드 없음 |
| 문서 단일 소스 | 중하 | USER_GUIDE/DEVELOPER 갱신, CLAUDE/README 지연 |
| 배포 재현성 | 중 | hiddenimports 명시 누락 위험 |
| 동시성 규율 | 중 | 파이프라인 락은 견고; **신규 위자드 스레드는 규율 미흡** |
| 계획→구현 추적 | 중하 | 기능은 동작하나 리포 스펙/태스크 산출물 약함 |

**결론**: 신규 기능의 **가치와 아키텍처 방향은 타당**하나, Superpowers 리뷰어 기준으로는 **스레드 안전성·배포 메타·문서 동기화·폴백 투명성**을 1단계로 닫기 전에는 “완료·견고”로 판정하기 어렵다. 코드 수정은 이 감사 문서의 1단계 항목부터 착수하는 것을 권장한다.

---

## 부록 A. CodeGraph 기준 영향 범위 (신규 기능)

| 심볼 | 주요 호출자 | 테스트 |
|------|-------------|--------|
| `analyze_page` / `discover_feeds` | `selector_wizard` | 단위 (html) |
| `evaluate_selector` | `selector_wizard` | 단위 |
| `CssSelectorScraper.fetch_articles` | 파이프라인, 위자드 미리보기, `preview_css_scrape` | 단위 일부 |
| `SelectorWizardPanel` | `sites._open_site_dialog` | **없음** |
| `save_site` (클로저) | 사이트 다이얼로그 | **없음** |

## 부록 B. 감사 방법 메모

- 우선: README, CLAUDE, CodeGraph explore (selector / css / wizard / SyncService / uploader sanitize)  
- 보조: grep (`link_selector`, hiddenimports, CLAUDE 스키마), 관련 pytest  

---

## 8. Remediation Status (2026-08-03 구현)

| 감사 항목 | 상태 | 반영 위치 |
|-----------|------|-----------|
| 이슈1 after/TclError/`_busy` | ✅ | `selector_wizard.py` — `_dialog_alive`, `_schedule`, `_req_gen`, finally 성격 해제 |
| 이슈2 워커 상태 직접 갱신 | ✅ | `_finish_test` 메인 스레드에서만 `_html`/`_analysis` 할당 |
| 이슈3 probe 지연·내부 URL | ✅ | `discover_feeds` budget/max_probes; `is_private_or_local_url` + GUI 확인 |
| 이슈4 목록 본문 폴백 투명성 | ✅ | `content_fallback_count`, `_content_fallback`, 미리보기 경고 |
| 이슈5 hiddenimports | ✅ | `x3_websync.spec` |
| 이슈6 선택자 검증 | ✅ | `validate_site` + GUI `save_site` |
| 이슈7 문서 드리프트 | ✅ | CLAUDE/README/USER_GUIDE(기존) |
| 이슈8 reparse | ✅ | `_reparse_fragment` |
| 파이프라인 중 미리보기 경고 | ✅ | `is_pipeline_running` 콜백 |
| 계약·회귀 테스트 | ✅ | `test_audit_selector_fixes.py`, validator 확장 |

**의도적 범위 밖**: 웹 대시보드 분석 API, live 네트워크 CI 프로브.
