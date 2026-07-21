# 개발자 가이드

일반 사용법은 [USER_GUIDE.md](USER_GUIDE.md), 저장소 개요는 루트 [README.md](../README.md)를 보세요.  
이 문서는 **코드 구조·테스트·빌드** 등 개발 시 참고 내용입니다.

아키텍처·기능 확장 로드맵의 더 긴 설명은 루트 `CLAUDE.md`를 참고하세요.

---

## 1. 모듈 구성

```
xteink-x3-websync/
├── x3_websync.py              # 진입점 (CLI/GUI, 단일 인스턴스 락)
├── websync/                  # 메인 패키지
│   ├── core/                 # paths, article, logger, process_lock
│   ├── config/               # ConfigManager, validator
│   ├── db/                   # SyncHistoryDb
│   ├── scrapers/             # 스크래퍼 + factory + 한국 프리셋
│   ├── epub/                 # builder + css/cover/sanitize + themes/
│   ├── upload/               # uploader, device_client, host, remote_path
│   ├── pipeline/             # service 파사드 + sync/preview/selected
│   ├── backup/               # 클라우드 백업 (sites.json + synced_posts.json)
│   ├── integrations/         # Calibre, ToastNotifier
│   ├── scheduler/            # schtasks / launchd / crontab
│   ├── servers/              # OPDS + web dashboard
│   ├── watch/                # Calibre 폴더 감시
│   └── gui/                  # app_core, sync_tab, device_files, settings_tab …
├── tests/                    # pytest
├── scripts/                  # 마이그레이션·실사이트 검증 등
└── docs/                     # 사용자·개발 문서
```

| 패키지 | 역할 |
|--------|------|
| `x3_websync.py` | 진입점 — GUI / `--sync` |
| `websync.core` | 경로, 로깅, 프로세스 락, 기사 URL 유틸 |
| `websync.config` | `config.json` CRUD, 검증 |
| `websync.pipeline` | 동기화·프리뷰·선택 전송 오케스트레이션 |
| `websync.scrapers` | 사이트별 수집기 + `ScraperFactory` + 프리셋 |
| `websync.epub` | EPUB 빌드 (테마·표지·정제) |
| `websync.upload` | 무선 업로드, 기기 파일 API |
| `websync.db` | 전송 이력 SQLite |
| `websync.backup` | OneDrive 등 폴더 미러 (sites/이력) |
| `websync.gui` | Tkinter GUI |
| `websync.scheduler` | OS 스케줄 등록 |
| `websync.servers` | OPDS · 웹 대시보드 |
| `websync.watch` | Calibre 폴더 감시 |

---

## 2. 스크래퍼 타입

현재 등록 타입은 `websync/scrapers/types.py` 의 `SCRAPER_TYPES` 가 단일 기준입니다.  
GUI·validator·factory 가 이 목록을 공유합니다.

| 타입 | 모듈 | 비고 |
|------|------|------|
| `css` | `css.py` | 사용자 CSS 선택자 |
| `rss` | `rss.py` | RSS/Atom |
| `velog` | `velog.py` | 프로필 URL → Velog RSS |
| `naver` | `naver.py` | 네이버 블로그 |
| `tistory` | `tistory.py` | 티스토리 RSS + 본문 |
| `brunch` | `brunch.py` | 브런치 API + 본문 |
| `newneek` | `newneek.py` | 뉴닉 사이트맵 + `__NEXT_DATA__` |
| `youtube` | `youtube.py` | 자막 (선택 의존성) |
| `substack` | `substack.py` | Substack |
| `naver_cafe` | `naver_cafe.py` | 공개 카페 |
| `naver_post` | `naver_post.py` | **서비스 종료** (명확한 예외) |
| `soonsal` | `soonsal.py` | 순살브리핑 |
| `moneyletter` | `moneyletter.py` | 어피티 머니레터 |

한국 추천 프리셋: `websync/scrapers/presets.py`  
새 스크래퍼 추가 절차는 `CLAUDE.md` §6 참고.

### 실사이트 스모크 검증

외부 네트워크 필요. **CI 기본 스위트에는 넣지 마세요.**

```bash
python scripts/validate_korean_scrapers.py
python scripts/validate_korean_scrapers.py --only naver,tistory,brunch,velog,newneek
python scripts/validate_korean_scrapers.py --include-optional --json output/scraper_validation.json
```

픽스처 기반 회귀 테스트(네트워크 없음):

```bash
python -m pytest tests/test_scraper_fixtures.py tests/test_brunch_scraper.py -q
```

---

## 3. 실행·설정 동작 요약

| 항목 | 동작 |
|------|------|
| X3 주소 | IP 또는 `crosspoint.local` |
| 다중 기기 | GUI 등록, IP·표시 이름 중복 불가 |
| 기기 파일 | File Transfer 모드; `device_files.default_upload_path` 가 뉴스/Calibre 업로드에도 적용 |
| 동기화 이력 | URL + `device_ip` 단위, 성공 기기만 기록 |
| 부분 재시도 | 미수신 기기만 재업로드 |
| GUI ↔ `--sync` | 프로세스 파일 락으로 직렬화 |

### 보안·프라이버시

- **OPDS**: 기본 localhost 무인증. LAN 공개 시 API 키 필수 (Bearer / `X-Api-Key`). 쿼리 `?api_key=` 는 기본 비활성 (`X3_OPDS_ALLOW_QUERY_API_KEY=1` 로만 허용).
- **웹 대시보드 LAN**: HTTP 평문 — 신뢰 네트워크에서만.
- **AI 요약·번역**: 기사 본문이 외부 API로 전송될 수 있음. 키는 `config.json` 로컬 저장.

---

## 4. 의존성

| 구분 | 내용 |
|------|------|
| 필수 | `requirements.txt` — requests, beautifulsoup4, lxml, ebooklib 등 |
| 선택 | `requirements-optional.txt` — Pillow, googletrans, youtube-transcript-api, watchdog |
| 외부 | Calibre (`calibredb`) — 서재 연동 시 |

Python 3.10+ 권장.

---

## 5. 테스트

```bash
python -m pytest tests/ -q
```

주요 영역: config, db, pipeline, scrapers(픽스처), epub, uploader, servers, process_lock 등.

---

## 6. Windows EXE 빌드 (PyInstaller)

```bash
pip install pyinstaller
pyinstaller x3_websync.spec
```

결과: `dist/x3_websync.exe` (GUI, 콘솔 없음).

EXE는 실행 파일과 같은 폴더에 `config.json`, `sync_history.db`, `logs/`, `output/` 을 둡니다.

**스펙에서 제외되는 선택 기능** (`x3_websync.spec` excludes):

| 기능 | 제외 패키지 | 소스 실행 시 |
|------|-------------|--------------|
| EPUB 표지 이미지 | Pillow | optional 설치 |
| YouTube 자막 | youtube-transcript-api | 동일 |
| Calibre Watch | watchdog | 동일 |
| googletrans 번역 | googletrans | 동일 |

새 스크래퍼 추가 시 `x3_websync.spec` 의 `hiddenimports` 에 모듈을 넣어야 합니다.

---

## 7. 관련 문서

| 문서 | 용도 |
|------|------|
| [USER_GUIDE.md](USER_GUIDE.md) | 사용자 화면·설정 |
| [FEATURE_PROPOSALS.md](FEATURE_PROPOSALS.md) | 기능 제안 |
| [PROJECT_AUDIT.md](PROJECT_AUDIT.md) | 구버전 감사 아카이브 |
| 루트 [`PROJECT_AUDIT.md`](../PROJECT_AUDIT.md) | 최신 구현 감사 |
| `CLAUDE.md` (루트) | 전체 구조·확장 가이드 |
| `x3_websync.spec` | PyInstaller hiddenimports (스크래퍼 모듈 누락 주의) |
