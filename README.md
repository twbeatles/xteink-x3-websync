# Xteink X3 WebSync Manager 🚀

Xteink X3 (CrossPoint 펌웨어 기반) e-ink 리더기를 위한 통합 뉴스 스크래핑 및 Calibre 라이브러리 무선 동기화 GUI 매니저 툴입니다.

기존의 단일 웹 크롤링 스크립트를 **SOLID 원칙**에 맞춰 모듈별로 분리·재설계하여 유지보수성과 확장성을 높였습니다.

---

## 주요 기능 ✨

1. **다중 사이트 뉴스 수집 및 EPUB 빌드**
   - 스크래퍼: `css`, `rss`, `naver`, `tistory`, `brunch`, `youtube`, `substack`
   - 사이트별 이미지 포함/제거, 번역, AI 요약(선택) 지원
   - SQLite 이력 DB로 증분 동기화 (중복 전송 방지)
   - e-ink 최적화 한국어 EPUB 생성 (표지 자동 생성 옵션)

2. **Calibre 서재 무선 연동** — `calibredb.exe`로 도서 목록 조회·다중 선택 전송

3. **로컬 파일 직접 무선 전송** — EPUB/PDF/MOBI/TXT

4. **다중 X3 기기 동시 전송** — GUI에서 추가 기기 등록

5. **자동 스케줄러** — Windows `schtasks` / macOS `launchd` / Linux `crontab`

6. **동기화 이력 탭** — 전송 이력 조회·삭제(재전송 허용)

7. **OPDS 카탈로그 서버** — 생성 EPUB 브라우징 (기본 localhost)

8. **웹 대시보드** — 브라우저에서 동기화 트리거·로그 확인 (API 토큰 인증)

9. **Calibre Watch** — 폴더 감시 후 신규 파일 자동 전송

10. **실행 로그** — `logs/sync_YYYY-MM-DD.log` 자동 저장

---

## 프로젝트 모듈 구성 🏗️

```
xteink-x3-websync/
├── x3_websync.py              # 진입점 (CLI/GUI, 단일 인스턴스 락)
├── websync/                   # 메인 패키지 (SOLID 기반 모듈 분리)
│   ├── core/                  # paths, article, logger
│   ├── config/                # ConfigManager
│   ├── db/                    # SyncHistoryDb
│   ├── scrapers/              # 7종 스크래퍼 + factory
│   ├── epub/                  # EpubBuilder
│   ├── upload/                # X3Uploader (다중 기기)
│   ├── pipeline/              # SyncService, Summarizer, Translator
│   ├── integrations/          # CalibreManager, ToastNotifier
│   ├── scheduler/             # SchedulerManager
│   ├── servers/               # OPDSServer, WebDashboard
│   ├── watch/                 # CalibreWatcher
│   └── gui/                   # SyncAppGui
├── tests/                     # pytest 단위·통합 테스트
└── scripts/                   # 마이그레이션·검증 스크립트
```

| 패키지/모듈 | 역할 |
|-------------|------|
| `x3_websync.py` | 진입점 — `websync.*` 패키지 로드 |
| `websync.core` | 프로젝트 루트 경로, 기사 URL 유틸, 파일 로깅 |
| `websync.config` | `config.json` CRUD, deep merge |
| `websync.pipeline` | 동기화 파이프라인 오케스트레이터 |
| `websync.scrapers` | css/rss/naver/tistory/brunch/youtube/substack + 팩토리 |
| `websync.epub` | EPUB 빌더 |
| `websync.upload` | HTTP 업로드 (다중 기기) |
| `websync.db` | SQLite 동기화 이력 |
| `websync.gui` | Tkinter GUI |
| `websync.scheduler` | 크로스플랫폼 스케줄러 |
| `websync.servers` | OPDS·웹 대시보드 |
| `websync.watch` | Calibre 폴더 감시 |

---

## 사용 방법 💡

### 설치
```bash
pip install -r requirements.txt
```

### 실행
```bash
python x3_websync.py
```

### 백그라운드 동기화 (스케줄러용)
```bash
python x3_websync.py --sync
```

### 기본 설정
- **X3 주소**: Wi-Fi IP 또는 `crosspoint.local`
- **추가 기기**: GUI에서 다중 기기 등록
- **웹 대시보드**: `config.json`의 `web_dashboard.api_token`으로 인증 (자동 생성)

---

## 환경 요구사항 📦

- Python 3.10+
- 필수: `beautifulsoup4`, `ebooklib`, `requests`, `lxml`
- 선택: `Pillow`(표지), `googletrans`(번역), `youtube-transcript-api`, `watchdog`(폴더 감시)
- Calibre 연동 시 로컬 PC에 Calibre 설치 필요

### 테스트
```bash
python -m pytest tests/ -q
```

### Windows EXE 빌드 (PyInstaller)
```bash
pip install pyinstaller
pyinstaller x3_websync.spec
```
빌드 결과물: `dist/x3_websync.exe` (GUI 모드, 콘솔 없음)