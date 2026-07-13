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
- **추가 기기**: GUI에서 다중 기기 등록 (IP·표시 이름 중복 불가)
- **웹 대시보드**: `config.json`의 `web_dashboard.api_token`으로 인증 (자동 생성, 세션 약 7일)
- **동기화 이력**: URL·기기(`device_ip`) 단위 — 성공 기기만 이력 기록
- **부분 재시도**: 다음 동기화 시 **아직 받지 못한 기기만** 재업로드 (이미 성공한 기기는 스킵)
- **동시 실행**: GUI 수동 동기화와 스케줄 `--sync`는 프로세스 파일 락으로 직렬화됩니다

### 보안·프라이버시 참고
- **OPDS localhost**: 기본은 인증 없이 로컬 EPUB 제공 (LAN 공개 시 API 키 필수; Bearer/`X-Api-Key` 권장)
- **웹 대시보드 LAN**: HTTP 평문 — 신뢰 네트워크에서만 LAN 공개 사용
- **AI 요약·번역**: 활성화 시 기사 본문이 외부 API(OpenAI 등)로 전송될 수 있음. API 키는 `config.json`에 로컬 저장

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
단위·통합 테스트 (`pytest tests/`) — pipeline, db, servers, uploader, paths, process_lock, epub 등.

### Windows EXE 빌드 (PyInstaller)
```bash
pip install pyinstaller
pyinstaller x3_websync.spec
```
빌드 결과물: `dist/x3_websync.exe` (GUI 모드, 콘솔 없음)

**EXE 빌드 시 제외되는 선택 기능** (`x3_websync.spec` excludes):
| 기능 | 제외 패키지 | 소스 실행 시 |
|------|-------------|--------------|
| EPUB 표지 이미지 | Pillow | `requirements-optional.txt` |
| YouTube 자막 | youtube-transcript-api | 동일 |
| Calibre Watch | watchdog | 동일 |
| googletrans 번역 | googletrans | 동일 |

EXE는 실행 파일과 같은 폴더에 `config.json` / `sync_history.db` / `logs` / `output`을 둡니다.