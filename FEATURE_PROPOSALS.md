# 🔬 Xteink X3 WebSync — 프로젝트 심층 분석 및 기능 확장 제안서

> **작성일**: 2026-07-14  
> **분석 범위**: 전체 소스코드 (~5,039줄, 42개 파일), CLAUDE.md, README.md, PROJECT_AUDIT.md  
> **목적**: 현재 구현 현황 파악 및 신규 기능 추가 방향 수립

---

## 📊 1. 현재 프로젝트 현황 요약

### 1-1. 아키텍처 평가

| 항목 | 평가 | 비고 |
|------|------|------|
| **모듈 분리** | ⭐⭐⭐⭐⭐ | SOLID 원칙 준수, 13개 서브패키지 |
| **확장성** | ⭐⭐⭐⭐⭐ | ScraperFactory OCP, 설정 자동 보강 |
| **동시성 안전** | ⭐⭐⭐⭐⭐ | thread lock + process file lock |
| **에러 처리** | ⭐⭐⭐⭐ | 대부분 완전, 일부 `print()` 잔존 |
| **테스트** | ⭐⭐⭐⭐ | 63건 통과, GUI/Translator 테스트 공백 |
| **문서화** | ⭐⭐⭐⭐⭐ | CLAUDE.md, README.md, AUDIT.md 완비 |
| **보안** | ⭐⭐⭐⭐ | compare_digest, 입력검증, LAN HTTP는 의도적 |

### 1-2. 코드 규모 분석

| 모듈 | 파일 수 | 라인 수 | 비중 |
|------|---------|---------|------|
| `websync/gui/` | 2 | 1,553 | 30.8% |
| `websync/scrapers/` | 10 | 653 | 13.0% |
| `websync/servers/` | 3 | 587 | 11.7% |
| `websync/pipeline/` | 4 | 499 | 9.9% |
| `websync/config/` | 3 | 268 | 5.3% |
| `websync/core/` | 5 | 254 | 5.0% |
| `x3_websync.py` | 1 | 233 | 4.6% |
| `websync/db/` | 2 | 197 | 3.9% |
| `websync/scheduler/` | 2 | 193 | 3.8% |
| `websync/epub/` | 2 | 191 | 3.8% |
| `websync/upload/` | 2 | 141 | 2.8% |
| `websync/integrations/` | 3 | 138 | 2.7% |
| `websync/watch/` | 2 | 123 | 2.4% |
| `websync/__init__.py` | 1 | 9 | 0.2% |
| **합계** | **42** | **~5,039** | **100%** |

### 1-3. 이미 구현 완료된 기능 (CLAUDE.md 로드맵 대비)

| 로드맵 항목 | 상태 | 구현 위치 |
|-------------|------|-----------|
| A. 로그 파일 저장 | ✅ | `core/logger.py` |
| B. 출력 폴더 열기 | ✅ | `gui/app.py` |
| C. 진행률 표시바 | ✅ | `gui/app.py` |
| D. 동기화 이력 탭 | ✅ | `gui/app.py` + `db/history.py` |
| E. 티스토리 스크래퍼 | ✅ | `scrapers/tistory.py` |
| F. 브런치 스크래퍼 | ✅ | `scrapers/brunch.py` |
| G. YouTube 자막 수집 | ✅ | `scrapers/youtube.py` |
| H. Substack 스크래퍼 | ✅ | `scrapers/substack.py` |
| I. 이미지 선택 포함 | ✅ | `scrapers/base.py` |
| J. AI 요약 삽입 | ✅ | `pipeline/summarizer.py` |
| K. 전자책 표지 생성 | ✅ | `epub/builder.py` |
| L. 기사 번역 | ✅ | `pipeline/translator.py` |
| M. OPDS 서버 | ✅ | `servers/opds.py` |
| N. 다중 기기 전송 | ✅ | `upload/uploader.py` |
| O. 크로스플랫폼 스케줄러 | ✅ | `scheduler/manager.py` |
| P. Calibre Watch | ✅ | `watch/calibre.py` |
| Q. 웹 대시보드 | ✅ | `servers/web_dashboard.py` |

> **결론**: CLAUDE.md에 기록된 A~Q 로드맵의 **모든 항목이 구현 완료**되었습니다.  
> 따라서 이하 제안은 **완전히 새로운 기능 확장** 방향입니다.

---

## 🚀 2. 신규 기능 확장 제안

현재 아키텍처의 강점(팩토리 패턴, 모듈 분리, 설정 자동 보강)을 활용하여 추가할 수 있는 기능들을 **우선순위별**로 정리합니다.

---

### 🔴 HIGH — 핵심 UX/기능 강화

#### H1. 스크래핑 프리뷰 & 선택적 동기화
- **문제**: 현재는 "동기화" 버튼 클릭 시 수집·빌드·전송이 한 번에 실행되어, 어떤 기사가 수집될지 미리 확인 불가
- **제안**: 
  1. "프리뷰" 버튼 추가 → 스크래핑만 실행하여 수집 결과를 GUI 테이블에 표시
  2. 사용자가 체크박스로 원하는 기사만 선택
  3. "선택 동기화" 버튼으로 선택된 기사만 EPUB 빌드·전송
- **수정 모듈**: `gui/app.py` (프리뷰 UI), `pipeline/service.py` (단계 분리 API)
- **난이도**: ★★★☆☆
- **기대 효과**: 불필요한 기사 전송 방지, 사용자 제어권 강화

#### H2. 기사 북마크 & 즐겨찾기 시스템
- **문제**: 한번 수집·전송된 기사는 DB에 "전송 완료"로만 기록되어 재활용 불가
- **제안**:
  1. 이력 탭에서 "즐겨찾기" 표시 기능 (⭐ 아이콘)
  2. 즐겨찾기 기사들을 별도 컬렉션 EPUB으로 재빌드
  3. DB 스키마에 `bookmarked` BOOLEAN 컬럼 추가
- **수정 모듈**: `db/history.py`, `gui/app.py`, `epub/builder.py`
- **난이도**: ★★☆☆☆
- **기대 효과**: 중요 기사 아카이빙, 맞춤 전자책 생성

#### H3. 다크 모드 & 테마 시스템
- **문제**: 현재 라이트 테마 고정 (`#f8f9fa`). 장시간 사용 시 눈 피로
- **제안**:
  1. 다크/라이트 테마 토글 (GUI 상단 바)
  2. 테마 설정을 `config.json`에 저장 (`"theme": "light" | "dark"`)
  3. `ttk.Style` 기반 커스텀 테마 구현
- **수정 모듈**: `gui/app.py`, `config/manager.py`
- **난이도**: ★★★☆☆
- **기대 효과**: 사용자 편의성 향상, 야간 사용 최적화

#### H4. 시스템 트레이 상주 모드
- **문제**: GUI를 닫으면 Calibre Watch, OPDS/웹 서버 등 백그라운드 기능이 모두 중단
- **제안**:
  1. `pystray` 라이브러리로 시스템 트레이 아이콘 상주
  2. 트레이 메뉴: "GUI 열기", "즉시 동기화", "서버 상태", "종료"
  3. GUI 닫기 시 트레이로 최소화 (설정으로 "완전 종료"/"트레이 최소화" 선택)
- **수정 모듈**: `gui/app.py`, `x3_websync.py`
- **신규 모듈**: `websync/gui/tray.py`
- **의존성 추가**: `pystray`, `Pillow` (아이콘 생성)
- **난이도**: ★★★☆☆
- **기대 효과**: 백그라운드 서비스 상시 가동, UX 개선

---

### 🟡 MEDIUM — 콘텐츠 & 스크래퍼 확장

#### M1. Medium.com 전용 스크래퍼
- **문제**: Medium 블로그는 RSSScraper로 제목만 수집 가능, paywall 컨텐츠 접근 불가
- **제안**:
  1. RSS 피드 파싱 + 본문 접근 (RSS `content:encoded` 활용)
  2. Medium 특유 클래스(`article`, `section.meteredContent`) 대상 파싱
  3. paywall 컨텐츠 감지 시 경고 로그
- **수정 모듈**: `scrapers/medium.py` (신규), `scrapers/factory.py`
- **타입 이름**: `"medium"`
- **난이도**: ★★☆☆☆

#### M2. Pocket/Instapaper/Readwise 연동
- **문제**: 외부 "나중에 읽기" 서비스의 저장 기사를 가져올 방법 없음
- **제안**:
  1. Pocket API (`/v3/get`) 연동 → 저장 기사 목록 가져오기
  2. 미전송 기사만 필터링 후 EPUB 빌드·전송
  3. 전송 완료된 기사는 Pocket에서 "아카이브" 처리 (선택)
- **신규 모듈**: `websync/integrations/pocket.py`
- **설정 추가**: `"pocket": {"enabled": false, "consumer_key": "", "access_token": ""}`
- **난이도**: ★★★☆☆

#### M3. 전체 텍스트 검색 (Full-Text Search)
- **문제**: 과거 전송 이력에서 특정 키워드의 기사를 찾기 어려움
- **제안**:
  1. SQLite FTS5 가상 테이블로 기사 제목·본문 인덱싱
  2. GUI 이력 탭에 검색창 추가
  3. 검색 결과에서 바로 재전송 가능
- **수정 모듈**: `db/history.py` (FTS5 테이블), `gui/app.py` (검색 UI)
- **난이도**: ★★★☆☆

#### M4. EPUB 병합 모드 (일간 합본)
- **문제**: 현재 사이트별로 개별 EPUB 생성 → 여러 사이트를 구독하면 파일이 너무 많음
- **제안**:
  1. "합본 모드" 설정: 하루치 전체 기사를 하나의 EPUB으로 병합
  2. 사이트별 챕터 구분, 통합 목차 생성
  3. 설정: `"epub_merge_mode": "per_site" | "daily_digest"`
- **수정 모듈**: `pipeline/service.py`, `epub/builder.py`, `config/manager.py`
- **난이도**: ★★★☆☆
- **기대 효과**: 기기에서 파일 관리 편의성 향상

#### M5. 스크래핑 규칙 Import/Export
- **문제**: 사이트 스크래핑 설정을 다른 PC나 사용자와 공유하기 어려움
- **제안**:
  1. 사이트 설정을 JSON 파일로 내보내기/가져오기
  2. GUI에 "사이트 설정 내보내기", "사이트 설정 가져오기" 버튼
  3. 커뮤니티 공유용 표준 포맷 정의
- **수정 모듈**: `gui/app.py`, `config/manager.py`
- **난이도**: ★★☆☆☆

#### M6. 네이버 카페/포스트 스크래퍼
- **문제**: 네이버 블로그만 지원. 네이버 카페, 네이버 포스트는 미지원
- **제안**:
  1. 네이버 카페 RSS/웹 파싱 (로그인 불필요한 공개 카페)
  2. 네이버 포스트(post.naver.com) 시리즈 수집
  3. `NaverBlogScraper`의 스타일 정제 로직 재활용
- **신규 모듈**: `scrapers/naver_cafe.py`, `scrapers/naver_post.py`
- **타입 이름**: `"naver_cafe"`, `"naver_post"`
- **난이도**: ★★★☆☆

#### M7. 커스텀 CSS 테마 for EPUB
- **문제**: EPUB의 폰트·크기·줄간격만 조정 가능. 사용자 정의 CSS 불가
- **제안**:
  1. 사용자가 커스텀 CSS 파일 경로를 지정하면 EPUB에 주입
  2. 기본 제공 테마 프리셋 (밝은/어두운/세리프/산세리프)
  3. 설정: `"epub_custom_css": ""` 또는 `"epub_theme": "default"`
- **수정 모듈**: `epub/builder.py`, `config/manager.py`, `gui/app.py`
- **난이도**: ★★☆☆☆

---

### 🟢 LOW — 인프라 & 플랫폼 확장

#### L1. 통계 대시보드 (수집·전송 메트릭)
- **문제**: 일별/주별 수집·전송 통계를 확인할 방법 없음
- **제안**:
  1. DB에 통계 테이블 추가 (일별 수집 건수, 전송 성공/실패, 소요 시간)
  2. GUI에 "통계" 탭 추가 → 차트 시각화 (`matplotlib` 내장 or 텍스트 기반)
  3. 웹 대시보드에도 통계 API 추가
- **신규 모듈**: `websync/db/stats.py`
- **수정 모듈**: `pipeline/service.py`, `gui/app.py`, `servers/web_dashboard.py`
- **난이도**: ★★★☆☆

#### L2. Webhook/알림 연동 (Telegram, Discord, Slack)
- **문제**: 동기화 결과를 Windows 토스트 알림으로만 확인 가능
- **제안**:
  1. Telegram Bot API / Discord Webhook / Slack Incoming Webhook 연동
  2. 동기화 완료 시 결과 메시지 자동 전송
  3. 설정: `"notifications": {"telegram": {"enabled": false, "bot_token": "", "chat_id": ""}}`
- **수정 모듈**: `integrations/notifier.py` (확장), `config/manager.py`
- **난이도**: ★★☆☆☆

#### L3. 자동 업데이트 체크
- **문제**: 새 버전 출시 여부를 사용자가 수동으로 확인해야 함
- **제안**:
  1. GitHub Releases API로 최신 버전 확인
  2. GUI 시작 시 업데이트 알림 배너 표시
  3. 릴리즈 노트 표시 + 다운로드 링크
- **신규 모듈**: `websync/core/updater.py`
- **수정 모듈**: `gui/app.py`
- **난이도**: ★★☆☆☆

#### L4. 설정 프로필 시스템
- **문제**: 하나의 `config.json`만 사용 가능. 상황별(업무/개인/테스트) 설정 전환 불가
- **제안**:
  1. 다중 설정 프로필 지원 (`config_work.json`, `config_personal.json`)
  2. GUI에서 프로필 전환 드롭다운
  3. CLI: `--profile work` 옵션
- **수정 모듈**: `config/manager.py`, `x3_websync.py`, `gui/app.py`
- **난이도**: ★★★☆☆

#### L5. 비동기 병렬 스크래핑 (`asyncio`)
- **문제**: 스크래퍼가 순차적 `requests.get()` 사용 → 사이트가 많으면 느림
- **제안**:
  1. `aiohttp` + `asyncio` 기반 비동기 스크래핑
  2. `BaseScraper`에 `async fetch_articles()` 메서드 추가 (기존 동기 메서드 유지)
  3. `SyncService`에서 `asyncio.gather()`로 병렬 수집
- **수정 모듈**: `scrapers/*.py`, `pipeline/service.py`
- **의존성 추가**: `aiohttp`
- **난이도**: ★★★★☆
- **참고**: 기존 동기 방식과 호환 유지 필요

#### L6. 플러그인 시스템
- **문제**: 새 스크래퍼/기능 추가 시 코드 직접 수정 필요
- **제안**:
  1. `plugins/` 디렉토리에 Python 파일을 놓으면 자동 로드
  2. `ScraperFactory`에 런타임 스크래퍼 등록
  3. 플러그인 매니페스트(plugin.json)로 메타데이터 관리
- **신규 모듈**: `websync/core/plugin_loader.py`
- **수정 모듈**: `scrapers/factory.py`
- **난이도**: ★★★★☆

#### L7. Docker 컨테이너화
- **문제**: Windows 의존성이 강한 GUI 외에 CLI/서버 기능은 서버 배포 가능하나 패키징 부재
- **제안**:
  1. `Dockerfile` 작성 (CLI + OPDS + 웹 대시보드)
  2. `docker-compose.yml`로 NAS/서버 배포
  3. 환경 변수로 설정 오버라이드
- **신규 파일**: `Dockerfile`, `docker-compose.yml`, `.dockerignore`
- **난이도**: ★★★☆☆

---

## 🏗️ 3. 코드 품질 개선 제안

현재 코드베이스의 품질은 높은 편이나, 아래 항목을 개선하면 유지보수성이 더 향상됩니다.

### Q1. GUI 코드 분리 (1,553줄 → 탭별 모듈화)

```
websync/gui/
├── app.py              # 메인 윈도우 + 탭 조립 (~200줄)
├── tab_sync.py          # 뉴스 동기화 탭 (~400줄)
├── tab_calibre.py       # Calibre 서재 탭 (~300줄)
├── tab_history.py       # 동기화 이력 탭 (~200줄)
├── tab_settings.py      # 서버 설정 탭 (~300줄)
├── bottom_bar.py        # 하단 동기화 버튼/로그 (~150줄)
└── widgets.py           # 공통 위젯 (ScrollContainer 등)
```

### Q2. 로깅 통일
- 일부 스크래퍼(`BrunchScraper`, `TistoryScraper`)에서 `print()` 직접 사용
- 모든 모듈에서 `get_logger()` 사용으로 통일 권장

### Q3. 타입 힌트 강화
- `pipeline/service.py`의 `log_callback`, `progress_callback` 파라미터에 `Callable` 타입 힌트 추가
- `dict` 반환 타입을 `TypedDict`로 명확화

### Q4. 웹 대시보드 HTML 분리
- `web_dashboard.py`에 384줄의 HTML이 Python 문자열로 인라인
- `websync/servers/templates/` 디렉토리로 분리 권장

### Q5. 설정 스키마 검증
- 현재 deep merge로 결손 키만 보강
- JSON Schema 또는 `pydantic` 기반 정형 검증 추가 가능

---

## 📋 4. 구현 우선순위 매트릭스

> 영향도(Impact)와 구현 난이도(Effort)를 기준으로 정렬

```
  Impact ↑
  높음 │ H1(프리뷰)  H4(트레이)   L5(비동기)
       │ H3(다크모드)  M4(합본)   L6(플러그인)
       │ H2(북마크)  M2(Pocket)   L7(Docker)
       │ M5(Export)  M3(검색)    L4(프로필)
  낮음 │ M7(CSS)   L2(Webhook)   L3(업데이트)
       │ M1(Medium) M6(카페)    L1(통계)
       └──────────────────────────────────────→ Effort
        낮음                                높음
```

### 🎯 추천 구현 순서

| 단계 | 기능 | 이유 |
|------|------|------|
| **1단계** | H1 (프리뷰 & 선택 동기화) | 핵심 UX 개선, 기존 코드 활용 용이 |
| **1단계** | H3 (다크 모드) | 사용자 요청 빈도 높음, 비교적 독립적 |
| **1단계** | M5 (사이트 설정 Export) | 간단하지만 실용적, 공유 편의성 |
| **2단계** | H2 (북마크/즐겨찾기) | DB 스키마 변경 필요하나 간단 |
| **2단계** | M4 (일간 합본 EPUB) | e-ink 사용성 대폭 개선 |
| **2단계** | H4 (시스템 트레이) | 백그라운드 서비스 상시 가동 |
| **3단계** | M1~M6 (스크래퍼/연동 확장) | 팩토리 패턴으로 쉽게 추가 |
| **3단계** | L2 (Webhook 알림) | 원격 모니터링 |
| **4단계** | Q1~Q5 (코드 품질) | 장기 유지보수성 |
| **5단계** | L5~L7 (인프라) | 고급 사용자/서버 배포 |

---

## 🔧 5. 기능별 구현 가이드 (상세)

### H1. 프리뷰 & 선택 동기화 — 구현 설계

#### 5-1-1. `pipeline/service.py` 변경

```python
# 기존 run_sync_pipeline()을 2단계로 분리

def preview_articles(self) -> list[dict]:
    """스크래핑만 실행하여 수집 가능한 기사 목록 반환 (EPUB 빌드/전송 없음)"""
    # 1. config 리로드
    # 2. enabled_sites 순회
    # 3. ScraperFactory로 수집
    # 4. needs_sync 필터
    # 5. 결과 반환 (빌드/전송 없이)
    return [{"site": "...", "title": "...", "url": "...", "content": "...", "selected": True}]

def sync_selected_articles(self, articles: list[dict]) -> bool:
    """선택된 기사들만 EPUB 빌드 및 전송"""
    # 기존 파이프라인의 빌드·전송 부분만 실행
```

#### 5-1-2. `gui/app.py` 변경

```python
# 프리뷰 결과 표시용 Treeview
preview_tree = ttk.Treeview(frame, columns=("site", "title", "url"), selectmode="extended")
# 체크박스 컬럼 추가
# "프리뷰" 버튼 → preview_articles() 호출
# "선택 동기화" 버튼 → sync_selected_articles() 호출
```

---

### H3. 다크 모드 — 구현 설계

#### 5-3-1. 테마 정의

```python
THEMES = {
    "light": {
        "bg": "#f8f9fa",
        "fg": "#212529",
        "accent": "#0d6efd",
        "card_bg": "#ffffff",
        "border": "#dee2e6",
        # ...
    },
    "dark": {
        "bg": "#1a1a2e",
        "fg": "#e0e0e0",
        "accent": "#4dabf7",
        "card_bg": "#16213e",
        "border": "#2a2a4a",
        # ...
    }
}
```

#### 5-3-2. `config.json` 스키마 추가

```json
{
  "theme": "light"
}
```

---

### M4. 일간 합본 EPUB — 구현 설계

#### 5-4-1. `pipeline/service.py` 변경

```python
if config.get("epub_merge_mode") == "daily_digest":
    # 모든 사이트의 기사를 하나의 리스트로 병합
    # site_name을 챕터 구분자로 사용
    all_articles_by_site = {}
    for site in enabled_sites:
        articles = scraper.fetch_articles(site)
        all_articles_by_site[site["name"]] = articles
    
    # 통합 EPUB 빌드
    epub_builder.build_digest(all_articles_by_site, date=today)
```

---

## 📐 6. 설정 스키마 확장 로드맵

신규 기능에 필요한 `config.json` 스키마 변경 사항:

```json
{
  "config_version": 3,
  
  "theme": "light",
  
  "epub_merge_mode": "per_site",
  "epub_custom_css": "",
  
  "notifications": {
    "telegram": {"enabled": false, "bot_token": "", "chat_id": ""},
    "discord": {"enabled": false, "webhook_url": ""},
    "slack": {"enabled": false, "webhook_url": ""}
  },
  
  "pocket": {
    "enabled": false,
    "consumer_key": "",
    "access_token": ""
  },
  
  "system_tray": {
    "minimize_to_tray": true,
    "start_minimized": false
  },
  
  "update_check": {
    "enabled": true,
    "last_check": ""
  }
}
```

> `ConfigManager`의 `_deep_merge()` 로직이 기존 사용자 설정에 새 키를 자동 보강하므로 하위 호환성이 보장됩니다.

---

## 📎 7. 참고: 새 스크래퍼 추가 체크리스트

`CLAUDE.md` §6에 정의된 절차를 준수합니다:

1. `websync/scrapers/{type_name}.py` 생성 — `BaseScraper` 상속
2. `fetch_articles(site_config) -> list[dict]` 구현
3. `scrapers/factory.py`의 `_scrapers` dict에 등록
4. `gui/app.py`의 `type_cb` Combobox values에 타입 추가
5. `config/manager.py` DEFAULT_CONFIG에 필요한 사이트 설정 추가
6. `tests/test_scraper_{type_name}.py` 테스트 작성
7. `CLAUDE.md`, `README.md` 문서 업데이트

반환 딕셔너리 형식:
```python
{"title": str, "content": str, "url": str}
```

---

## 🏁 8. 결론

Xteink X3 WebSync Manager는 **CLAUDE.md에 기록된 17개 로드맵 항목을 모두 구현 완료**한 성숙한 프로젝트입니다. 약 5,039줄의 코드가 SOLID 원칙에 따라 13개 서브패키지로 잘 분리되어 있으며, 63개의 테스트가 통과하고 있습니다.

본 문서에서 제안하는 **16개 신규 기능**(HIGH 4개, MEDIUM 7개, LOW 7개)과 **5개 코드 품질 개선 항목**은 기존 아키텍처를 크게 변경하지 않고도 점진적으로 추가할 수 있습니다.

특히 **1단계로 권장하는 3개 기능**(프리뷰 & 선택 동기화, 다크 모드, 사이트 설정 Export)은 사용자 경험을 즉각적으로 개선하면서도 구현 난이도가 낮아 빠른 릴리즈가 가능합니다.
