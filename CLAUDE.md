# CLAUDE.md — 개발자 가이드 & 기능 확장 로드맵

> **Xteink X3 WebSync Manager** 프로젝트의 완전한 구조 분석 및 향후 기능 확장 아이디어를 정리한 내부 개발 문서입니다.  
> 새로운 기능 추가, 버그 수정, 구조 변경 시 이 문서를 먼저 참조하세요.

---

## 1. 프로젝트 개요

**목적**: Xteink X3 (CrossPoint 펌웨어) e-ink 리더기를 위한 통합 뉴스·콘텐츠 수집 → EPUB 빌드 → 무선 전송 자동화 GUI 툴

**핵심 가치**:
- 매일 아침 지정한 뉴스 소스(일반 웹, RSS, 네이버 블로그)를 자동 수집해 e-ink 기기에 최적화된 EPUB 전자책으로 빌드 및 전송
- 이미 보낸 기사는 SQLite DB로 중복 제거 (증분 동기화)
- Calibre 도서관과 연동해 PC 서재의 책을 무선 즉시 전송

**개발 원칙**: SOLID, 모듈 단일 책임, Python 타입 힌트 적용

---

## 2. 프로젝트 파일 구조 전체 분석

```
xteink-x3-websync/
├── x3_websync.py         # 진입점 (Entrypoint) — CLI/GUI 분기, 단일 인스턴스 락
├── config_manager.py     # 설정 파일 CRUD — threading.Lock 보호, 결손 키 자동 보강
├── service.py            # 동기화 파이프라인 오케스트레이터 (비즈니스 로직 핵심)
├── scrapers.py           # 콘텐츠 수집기 — CSS / RSS / 네이버 전용 (팩토리 패턴)
├── builder.py            # EPUB 빌더 — e-ink 맞춤 CSS, UTF-8 한국어 지원
├── uploader.py           # 기기 무선 업로드 — 파일명 세니타이징, 가변 타임아웃
├── calibre.py            # Calibre DB 연동 — calibredb.exe 래퍼
├── scheduler.py          # 윈도우 작업 스케줄러 제어 — 경로 고정, 인젝션 방어
├── notifier.py           # 윈도우 토스트 알림 — 매개변수 분리형 안전 구현
├── db_manager.py         # SQLite 동기화 이력 — threading.Lock, timeout=10.0
├── gui.py                # Tkinter 다크 테마 GUI — 탭 인터페이스
│
├── config.json           # 사용자 설정 (gitignore 적용)
├── sync_history.db       # 전송 이력 SQLite DB (gitignore 적용)
├── output/               # 생성된 EPUB 저장 디렉토리 (gitignore 적용)
│
├── README.md             # 사용자용 설명서
├── PROJECT_AUDIT.md      # 보안·기능 감사 보고서 (이미 반영 완료)
├── CLAUDE.md             # 본 문서: 개발자 구조 분석 + 기능 확장 가이드
├── pyrightconfig.json    # Pyright 정적 타입 검사 설정
└── .gitignore            # 민감 파일 배포 제외
```

---

## 3. 모듈별 상세 분석

### 3-1. `x3_websync.py` — 진입점

| 항목 | 내용 |
|------|------|
| 역할 | CLI `--sync` 플래그 분기 / GUI 앱 기동 |
| 보안 패치 | `NullWriter` 클래스로 pythonw.exe stdout=None 방어 |
| 다중 실행 방지 | `os.O_CREAT | os.O_WRONLY | os.O_EXCL` 기반 락 파일 (`/tmp/x3_websync_instance.lock`) |
| 주의 | 락 파일은 `finally`에서 항상 해제됨 |

**호출 관계**:
```
main()
  ├── acquire_instance_lock()
  ├── ConfigManager()
  ├── SyncService(config_manager)
  └── [--sync] service.run_sync_pipeline()
      [GUI]   SyncAppGui(service).run()
```

---

### 3-2. `config_manager.py` — 설정 관리자

| 항목 | 내용 |
|------|------|
| 역할 | `config.json` 로드·저장, 결손 키 자동 보강 |
| 동시성 보호 | `threading.Lock()` 클래스 수준 락 |
| 내부 메서드 | `_save_config_unlocked()` — 락 내부에서 호출하는 전용 저장 함수 |

**설정 스키마** (`config.json`):
```json
{
  "x3_ip": "crosspoint.local",
  "output_dir": "./output",
  "calibre_path": "C:\\Program Files\\Calibre2\\calibredb.exe",
  "font_family": "serif",
  "font_size": 16,
  "line_height": 1.7,
  "sites": [
    {
      "name": "사이트명",
      "type": "css | rss | naver",
      "url": "https://...",
      "item_selector": ".post-item",
      "title_selector": ".post-title",
      "content_selector": ".post-content",
      "remove_selectors": ".ad, #comments",
      "limit": 5,
      "enabled": true
    }
  ],
  "schedule": {
    "enabled": false,
    "hour": "07",
    "minute": "00"
  }
}
```

---

### 3-3. `service.py` — 동기화 파이프라인 오케스트레이터

| 항목 | 내용 |
|------|------|
| 역할 | 스크래핑 → 중복 필터 → EPUB 빌드 → 기기 업로드 전 과정 총괄 |
| 중복 필터 | `SyncHistoryDb.is_synced(url)` 로 이미 보낸 기사 스킵 |
| 결과 반환 | `bool` — True: 전송 성공 또는 신규 기사 없음 / False: 전송 실패 |

**파이프라인 흐름**:
```
run_sync_pipeline()
  1. config 최신 리로드
  2. enabled_sites 필터링
  3. for each site:
     a. ScraperFactory.get_scraper(type).fetch_articles(site)
     b. [신규 기사] = is_synced() 필터링
     c. EpubBuilder.build(name, new_articles) → epub_path
     d. X3Uploader.upload(epub_path)
     e. [성공 시] db.mark_synced(url, name, title)
  4. ToastNotifier.show_toast(결과)
```

---

### 3-4. `scrapers.py` — 콘텐츠 수집기 (팩토리 패턴)

| 클래스 | 타입 | 방식 |
|--------|------|------|
| `BaseScraper` | ABC | 추상 기반 클래스 |
| `CssSelectorScraper` | `"css"` | CSS 선택자로 HTML 파싱 |
| `RssScraper` | `"rss"` | RSS/Atom XML 파싱 |
| `NaverBlogScraper` | `"naver"` | RSS 리스팅 + PostView.naver iframe 우회 |
| `ScraperFactory` | — | `.get_scraper(type)` / `.register_scraper()` |

**NaverBlogScraper 특이사항**:
- 블로그 ID 추출: `blog.naver.com/ID`, `m.blog.naver.com/ID`, `ID.blog.me` 세 가지 주소 형식 지원
- 본문 추출: `div.se-main-container` (스마트에디터 One) 또는 `#postViewArea` (구버전)
- 서식 박멸: 모든 `style`, `class` 속성 강제 삭제 → 배경색·글자색 초기화
- 이미지 제거: e-ink 최적화를 위해 모든 `img` 태그 decompose

---

### 3-5. `builder.py` — EPUB 빌더

| 항목 | 내용 |
|------|------|
| 역할 | 기사 배열을 받아 단일 EPUB 파일 생성 |
| 의존성 | `ebooklib` |
| 언어 메타 | `lang="ko"` 설정, UTF-8 인코딩 명시 |
| CSS | `font-family`, `font-size`, `line-height` 설정 가능 |
| 파일명 | `{site_name}_{YYYY-MM-DD}.epub` |

---

### 3-6. `uploader.py` — 기기 무선 업로드

| 항목 | 내용 |
|------|------|
| 역할 | X3 기기의 `/upload` HTTP 엔드포인트로 파일 POST |
| 파일명 | 영숫자·하이픈·언더바만 허용 (CrossPoint 크래시 방지) |
| 타임아웃 | `25초 + (파일크기_MB × 5초)` 동적 계산 |
| 연결 테스트 | `GET /` 3초 타임아웃으로 기기 생존 여부 확인 |

---

### 3-7. `calibre.py` — Calibre 연동

| 항목 | 내용 |
|------|------|
| 역할 | `calibredb.exe` CLI 래퍼 |
| `list_books()` | `--to-json` 플래그로 JSON 파싱 |
| `get_book_file_path()` | EPUB > PDF > MOBI > TXT 우선순위로 파일 경로 반환 |

---

### 3-8. `scheduler.py` — 스케줄러

| 항목 | 내용 |
|------|------|
| 역할 | Windows `schtasks` 기반 일간 스케줄 등록/해제 |
| 보안 | `hour/minute` 입력 정수 범위 검증, `shell=False` 인자 리스트 실행 |
| 경로 고정 | `cmd.exe /c "cd /d <project_dir> && pythonw ..."` |

---

### 3-9. `notifier.py` — 알림

| 항목 | 내용 |
|------|------|
| 역할 | 윈도우 BalloonTip 시스템 알림 |
| 보안 | 스크립트와 데이터 분리: `$args[0]`, `$args[1]`, `$args[2]` 사용 |

---

### 3-10. `db_manager.py` — SQLite 이력 DB

| 항목 | 내용 |
|------|------|
| 역할 | 전송 완료된 포스트 URL 영구 이력 관리 |
| 동시성 | `threading.Lock()` + `sqlite3.connect(timeout=10.0)` |
| 테이블 | `synced_posts(url PK, site_name, title, synced_at)` |

---

### 3-11. `gui.py` — GUI

| 항목 | 내용 |
|------|------|
| 프레임워크 | `tkinter` + `ttk` |
| 테마 | Catppuccin Mocha 다크 팔레트 (`#1e1e2e` 계열) |
| 탭 구조 | `뉴스 동기화 및 일반설정` / `Calibre 서재 연동` |
| 비동기 | `threading.Thread(daemon=True)` + `root.after(0, callback)` 패턴 |

---

## 4. 데이터 흐름 다이어그램

```
[사용자 / 윈도우 스케줄러]
           │
           ▼
   x3_websync.py (진입점)
     ┌─────┴──────┐
   GUI          --sync (백그라운드)
     │              │
     └──────┬────────┘
            │
            ▼
  SyncService.run_sync_pipeline()
            │
            ├─ ConfigManager.load_config()       ──► config.json
            │
            ├─ ScraperFactory.get_scraper(type)
            │     ├─ CssSelectorScraper          ──► 일반 웹 HTML
            │     ├─ RssScraper                  ──► RSS/Atom XML
            │     └─ NaverBlogScraper            ──► 네이버 RSS + PostView API
            │
            ├─ SyncHistoryDb.is_synced(url)      ──► sync_history.db (중복 제거)
            ├─ EpubBuilder.build()               ──► output/*.epub
            ├─ X3Uploader.upload()               ──► http://{x3_ip}/upload (기기 전송)
            ├─ SyncHistoryDb.mark_synced()       ──► sync_history.db (이력 기록)
            └─ ToastNotifier.show_toast()        ──► 윈도우 토스트 알림
```

---

## 5. 기능 확장 아이디어 (Feature Roadmap)

현재 아키텍처는 SOLID 원칙 기반으로 설계되어 있어 아래 기능들을 비교적 깔끔하게 추가할 수 있습니다.

---

### 🔴 HIGH — 핵심 UX 개선

#### A. 동기화 실행 로그 파일 저장
- **설명**: `logging` 모듈을 사용해 동기화 실행 기록을 날짜별 파일(`logs/sync_YYYY-MM-DD.log`)에 자동 저장
- **수정 모듈**: `x3_websync.py`, `service.py`
- **Why**: 스케줄러 백그라운드 구동 시 문제 발생 여부를 추후 확인 불가능 → 로그 파일 필수

#### B. 출력 폴더 바로 열기 버튼
- **설명**: GUI에 "출력 폴더 열기" 버튼 추가 → `subprocess.Popen(['explorer', output_dir])`
- **수정 모듈**: `gui.py`
- **Why**: 현재 생성된 EPUB을 확인하려면 탐색기를 직접 열어야 함

#### C. 수집 진행률 표시바 (ProgressBar)
- **설명**: 동기화 실행 중 각 사이트별 수집 상태를 `ttk.Progressbar`로 시각화
- **수정 모듈**: `gui.py`, `service.py` (콜백 시그니처 확장)

#### D. 동기화 이력 조회 탭
- **설명**: `sync_history.db`에 기록된 전송 이력을 GUI 내 테이블로 조회하고, 특정 항목을 삭제해 재전송 가능하도록 구현
- **수정 모듈**: `db_manager.py` (삭제 메서드 추가), `gui.py` (이력 탭 추가)

---

### 🟡 MEDIUM — 스크래퍼 확장

#### E. 티스토리(Tistory) 전용 스크래퍼
- **설명**: 티스토리 블로그 RSS는 본문 요약만 제공하는 경우가 많아 `CssSelectorScraper`로 커버 불가. 전용 스크래퍼로 본문 직접 접근
- **수정 모듈**: `scrapers.py` (`TistoryScraper` 추가, `ScraperFactory` 등록)
- **타입 이름**: `"tistory"`

#### F. 브런치(Brunch) 전용 스크래퍼
- **설명**: 카카오 브런치는 작가 기반 장문 콘텐츠가 많고 CSS 구조가 특수. 전용 스크래퍼로 본문, 썸네일 텍스트, 작가명 추출
- **수정 모듈**: `scrapers.py` (`BrunchScraper` 추가)
- **타입 이름**: `"brunch"`

#### G. YouTube 채널 자막 수집 스크래퍼
- **설명**: YouTube 동영상 한국어 자막(자동생성 또는 수동)을 `youtube_transcript_api`로 수집해 EPUB 변환
- **수정 모듈**: `scrapers.py` (`YoutubeScraper` 추가)
- **타입 이름**: `"youtube"`
- **의존성 추가**: `pip install youtube-transcript-api`

#### H. Substack 뉴스레터 스크래퍼
- **설명**: Substack의 RSS 피드는 전체 HTML 본문을 제공. 현재 RssScraper로 기본 작동하나, Substack 특유의 레이아웃 클렌징 전용 처리 추가
- **수정 모듈**: `scrapers.py` (`SubstackScraper` 추가 또는 RssScraper 고도화)

---

### 🟡 MEDIUM — 콘텐츠 처리 개선

#### I. 이미지 선택적 포함 옵션
- **설명**: 사이트별로 이미지 포함 여부를 GUI 옵션으로 선택 가능하게 개선. 현재는 전체 제거
- **수정 모듈**: `scrapers.py`, `config_manager.py` (스키마: `"include_images": true/false`), `gui.py`

#### J. AI 기사 요약 삽입
- **설명**: OpenAI API 또는 로컬 Ollama LLM을 사용해 각 기사의 요약문을 자동 생성 후 EPUB 챕터 첫 문단에 삽입
- **수정 모듈**: `service.py` (파이프라인에 요약 단계 삽입), 신규 `summarizer.py` 모듈
- **설정 키 추가**: `"openai_api_key"`, `"ollama_host"`

#### K. 전자책 표지(Cover) 자동 생성
- **설명**: 날짜와 사이트명이 표시된 간단한 표지 이미지를 동적으로 생성해 EPUB에 첨부
- **수정 모듈**: `builder.py`
- **의존성 추가**: `pip install Pillow`

#### L. 기사 번역 기능 (한국어 외 언어 소스)
- **설명**: 영어 등 외국어 기사 수집 시 `googletrans` 또는 DeepL API를 통해 자동 번역 후 한국어 EPUB으로 빌드
- **수정 모듈**: `service.py`, 신규 `translator.py`

---

### 🟢 LOW — 플랫폼·인프라 확장

#### M. OPDS 카탈로그 서버 내장
- **설명**: 생성된 EPUB 파일들을 OPDS 표준으로 제공하는 경량 HTTP 서버 내장 → X3 기기의 OPDS 클라이언트에서 직접 브라우징 다운로드 가능
- **수정 모듈**: 신규 `opds_server.py`, `gui.py` (서버 시작/중지 버튼)

#### N. 다중 X3 기기 동시 전송 지원
- **설명**: 현재 단일 기기 주소만 지원. 여러 기기 주소를 목록으로 관리하고 `ThreadPoolExecutor`로 동시 전송
- **수정 모듈**: `config_manager.py` (스키마: `"x3_devices": [...]`), `uploader.py`, `gui.py`

#### O. 크로스플랫폼 알림 및 스케줄러 (macOS/Linux)
- **설명**: 현재 `notifier.py`와 `scheduler.py`는 Windows 전용. `plyer` 라이브러리로 알림 추상화, macOS `launchd` / Linux `cron` 지원
- **수정 모듈**: `notifier.py`, `scheduler.py`

#### P. Calibre 서재 자동 Watch 동기화
- **설명**: Calibre 서재 폴더를 `watchdog` 라이브러리로 감시. 새 책 추가 시 자동으로 X3 기기에 전송
- **수정 모듈**: `calibre.py`, `service.py`, 신규 `watcher.py`
- **의존성 추가**: `pip install watchdog`

#### Q. 웹 UI 대시보드
- **설명**: Tkinter GUI 외에 FastAPI 기반 웹 인터페이스 제공. 원격 브라우저에서 동기화 제어 및 로그 확인 가능
- **수정 모듈**: 신규 `web_api.py`

---

## 6. 새 스크래퍼 추가 방법 (개발 가이드)

`scrapers.py`에 새 스크래퍼를 추가하는 것은 3단계면 충분합니다:

```python
# 1. BaseScraper를 상속하여 클래스 작성
class MyScraper(BaseScraper):
    def fetch_articles(self, site_config: dict) -> list:
        # 수집 로직 구현
        return [{"title": "제목", "content": "<p>본문HTML</p>", "url": "고유URL"}]

# 2. ScraperFactory에 등록
ScraperFactory._scrapers["my_type"] = MyScraper()

# 3. gui.py의 type_cb Combobox values 에 "my_type" 추가
type_cb = ttk.Combobox(frame, values=["css", "rss", "naver", "my_type"], ...)
```

반환 딕셔너리 형식을 반드시 준수해야 합니다:
```python
{
    "title": str,     # 기사 제목 (필수)
    "content": str,   # 본문 HTML 문자열 (필수)
    "url": str        # 고유 URL — 중복 감지 키로 사용 (필수)
}
```

---

## 7. 설정 스키마 확장 가이드

새 기능에 설정 항목이 필요하면 `ConfigManager.DEFAULT_CONFIG`에 먼저 추가합니다:

```python
DEFAULT_CONFIG = {
    ...
    "new_feature_option": "default_value",  # 여기에 추가
    ...
}
```

`load_config()`의 결손 키 자동 보강 로직이 기존 사용자의 `config.json`에 새 키를 자동으로 추가해 하위 호환성을 보장합니다.

---

## 8. 의존성 목록 및 역할

| 라이브러리 | 용도 | 필수 여부 |
|-----------|------|---------|
| `requests` | HTTP 요청 (스크래핑, 기기 업로드) | 필수 |
| `beautifulsoup4` | HTML/XML 파싱 | 필수 |
| `lxml` | XML 파서 백엔드 (RSS) | 필수 |
| `ebooklib` | EPUB 파일 생성 | 필수 |
| `tkinter` | GUI (Python 표준 내장) | 필수 |
| `sqlite3` | 동기화 이력 DB (Python 표준 내장) | 필수 |
| `Calibre` | 도서 서재 연동 (외부 설치) | 선택 |
| `Pillow` | 표지 이미지 생성 (예정) | 선택 (미구현) |
| `youtube-transcript-api` | YouTube 자막 수집 (예정) | 선택 (미구현) |
| `watchdog` | 파일 시스템 변경 감시 (예정) | 선택 (미구현) |

---

## 9. 자주 마주치는 이슈와 해결책

| 증상 | 원인 | 해결책 |
|------|------|--------|
| 스케줄러 실행 후 동기화 안됨 | 작업 경로 유실 → config.json 못 읽음 | `scheduler.py`의 `cd /d` 경로 확인 |
| `database is locked` 오류 | 동시 동기화 실행 | `db_manager.py`의 `timeout=10.0` 및 Lock 확인 |
| 네이버 포스트 본문 없음 | `div.se-main-container` 미발견 | `#postViewArea` 폴백 확인, 네이버 HTML 구조 변경 여부 점검 |
| CrossPoint 기기 크래시 | 한글/공백 파일명 전송 | `uploader.py` 세니타이징 로직 확인 |
| EPUB 한글 깨짐 | 인코딩 문제 | `builder.py`의 UTF-8 메타 선언 확인 |
| pythonw 실행 후 아무 일도 없음 | stdout=None 크래시 | `x3_websync.py`의 `NullWriter` 확인 |
| 동시 기동 시 config.json 손상 | Race Condition | `config_manager.py`의 `threading.Lock` 확인 |

---

## 10. Git 커밋 컨벤션

```
feat:      새 기능 추가
fix:       버그 수정
refactor:  코드 구조 변경 (기능 변화 없음)
security:  보안 취약점 수정
docs:      문서 수정
test:      테스트 추가/수정
chore:     빌드, 의존성, 설정 변경
```

예시:
```
feat(scrapers): Add TistoryScraper for Tistory blog support
security(notifier): Replace inline PowerShell string injection with args binding
fix(scheduler): Lock working directory using cmd /c cd /d before execution
feat(gui): Add sync history viewer tab with re-send capability
```
