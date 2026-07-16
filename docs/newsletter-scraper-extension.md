# Newsletter Scraper Extension Guide

> **목적**: soonsal.com 같은 일자별/아카이브 형식의 뉴스레터 사이트를 안정적으로 스크래핑하여 EPUB으로 변환하는 기능 확장.
> 이 문서는 **미래 AI 에이전트(Claude, Grok 등)** 가 동일한 패턴의 뉴스레터 사이트를 쉽게 추가할 수 있도록 설계 의도, 아키텍처, 사용법을 상세히 설명한다.

**추가된 날짜**: 2026-07-16
**관련 PR / 커밋**: (이 문서 작성 시점의 변경사항 참조)
**주요 파일**:
- `websync/scrapers/newsletter_base.py` (핵심 확장 베이스)
- `websync/scrapers/soonsal.py` (구체 구현 예시)
- `websync/scrapers/factory.py`
- `websync/config/validator.py`
- `websync/gui/sync_tab/sites.py`
- `x3_websync.spec`

---

## 1. 배경 및 동기

기존 스크래퍼 시스템:
- `CssSelectorScraper`: 일반 목록 페이지용 (item/title/content selector)
- `RssScraper`: RSS/Atom
- 전용 스크래퍼: naver, tistory, brunch, youtube, substack, naver_cafe, naver_post

뉴스레터(특히 한국어 브리핑 사이트)는 보통:
- `/newsletters/` 또는 `/archive/` 같은 **목록(아카이브) 페이지**
- `/newsletters/2026/0716.html` 같은 **날짜 기반 상세 페이지**
- 상세 페이지에 `<h1>`이 없거나 `<title>`에 주요 제목이 들어있음
- 시장 데이터, 섹션(📊, ☀️), 표, 리스트 등 구조화된 콘텐츠

`css` 타입으로 처리하기에는:
- 목록 파싱이 복잡 (링크만 있고 본문 없음)
- 상세 페이지 구조가 매번 달라 fallback 필요
- title/content 품질이 떨어짐

→ **전용 스크래퍼 + 재사용 가능한 베이스** 필요.

---

## 2. 설계 결정 (Architecture Decisions)

### 2.1 BaseNewsletterScraper 도입 (핵심)

`websync/scrapers/newsletter_base.py` 에 `BaseNewsletterScraper` (BaseScraper 상속) 추가.

**제공하는 공통 기능**:
- `fetch_articles()` 기본 구현 (list vs direct detail 분기)
- `_extract_links()` — `LINK_PATTERN` regex로 아카이브에서 링크 수집
- `_fetch_and_clean_detail()`
- `_find_content_container()` — `CONTENT_CANDIDATES` 순서대로 탐색 (의미 있는 텍스트 길이 > 150자)
- `_clean_content()` — nav/header/footer/script/style + 속성 최소화 (href/src/alt/title)
- `maybe_strip_images()` 연동
- `_get_title()` — `<title>` 태그 우선 사용
- `last_fetch_stats` 지원

**하위 클래스에서 오버라이드할 것** (최소):
```python
LINK_PATTERN = re.compile(r"...")
CONTENT_CANDIDATES = ["div.content", "article", ...]

def _clean_content(self, container, site_config):
    super()._clean_content(...)
    # 사이트별 추가 제거
```

이 설계로 **새 뉴스레터 사이트 추가 시 15~30줄 정도**만 작성하면 된다.

### 2.2 SoonsalScraper 구현 방식

```python
class SoonsalScraper(BaseNewsletterScraper):
    LINK_PATTERN = re.compile(r"/newsletters/\d{4}/\d{4}(-[a-zA-Z0-9]+)?\.html")
    CONTENT_CANDIDATES = ["div.content", "div.word-section", "div.wrapper", ...]

    def _clean_content(self, ...):
        super()...
        # 홈 링크, 푸터 등 추가 제거
```

**발견된 실제 구조** (2026-07-16 기준):
- 목록: `a[href*="/newsletters/"]` + 날짜별 두 개 링크 (브리핑 + Crypto)
- 상세: `<title>`이 가장 좋은 제목 소스 (H1 없음)
- 본문: `div.content` > `div.word-section` > `div.wrapper`

### 2.3 다른 선택지와 Trade-off

| 접근 | 장점 | 단점 | 선택 이유 |
|------|------|------|----------|
| 기존 `css` + `fetch_detail_page` 강화 | 변경 최소 | 목록 파싱 품질 낮음, title 추출 어려움, 유지보수 어려움 | ❌ |
| 완전 generic config-driven (list_selector + detail selectors) | 코드 추가 없이 config만 | 복잡한 정제 로직 표현 어려움, 깨지기 쉬움 | 부분 고려 |
| **전용 + BaseNewsletterScraper 상속** | 품질 최고, 확장 용이, 코드 명확 | 타입 하나당 한 파일 | ✅ 채택 |
| 모든 뉴스레터를 "soonsal" 타입으로 config 확장 | 등록 작업 줄음 | 단일 타입이 너무 비대해짐 | ❌ |

결론: **SOLID + OCP** 원칙 유지하면서, 뉴스레터 도메인에 맞는 작은 추상화 계층을 추가.

---

## 3. 사용 방법 (End User)

### GUI에서 추가

1. **뉴스 동기화** 탭 → **사이트 추가**
2. 타입 선택: **`soonsal`**
3. 이름: `순살브리핑` (또는 원하는 이름)
4. URL: `https://soonsal.com/newsletters/` (또는 특정 상세 페이지 URL)
5. limit: `1` ~ `3` 추천 (보통 하루 2건)
6. 이미지 포함: 필요시 체크 (기본 false 권장)
7. 저장 후 **프리뷰** 또는 **동기화** 실행

**결과**:
- `output/순살브리핑_2026-07-16.epub`
- 각 뉴스레터가 EPUB 내 별도 챕터로 들어감
- 기존 DB 중복 제거, 업로드, 스케줄러 모두 그대로 동작

### 직접 상세 URL 사용

특정 날짜만 수집하고 싶을 때:
```
https://soonsal.com/newsletters/2026/0716.html
```

---

## 4. 새 뉴스레터 사이트 추가 가이드 (AI / 개발자용)

### 단계별

1. **새 파일 생성**: `websync/scrapers/my_newsletter.py`

2. **Base 상속 구현** (예시):

```python
import re
from bs4 import BeautifulSoup
from websync.scrapers.newsletter_base import BaseNewsletterScraper

class MyNewsletterScraper(BaseNewsletterScraper):
    """예시: 다른 브리핑 사이트"""

    LINK_PATTERN = re.compile(r"/posts/\d{4}-\d{2}-\d{2}\.html")

    CONTENT_CANDIDATES = [
        "div.post-body",
        "article.main-content",
        "div#content",
        "main",
    ]

    def _clean_content(self, container: BeautifulSoup, site_config: dict) -> None:
        super()._clean_content(container, site_config)

        # 사이트 특화 제거
        for selector in [".newsletter-promo", ".ads", "footer .social"]:
            for el in container.select(selector):
                el.decompose()
```

3. **Factory 등록** (`websync/scrapers/factory.py`)

```python
from websync.scrapers.my_newsletter import MyNewsletterScraper
...
"my_newsletter": MyNewsletterScraper(),
```

4. **Validator** (`websync/config/validator.py`)

```python
valid_types = (..., "my_newsletter")
```

5. **GUI** (`websync/gui/sync_tab/sites.py`)

- Combobox values에 추가
- `on_type_change` disabled tuple에 추가

6. **PyInstaller** (`x3_websync.spec`)

```python
'websync.scrapers.my_newsletter',
```

7. **문서 업데이트**
   - `docs/newsletter-scraper-extension.md` 에 예시 추가
   - `README.md`, `docs/USER_GUIDE.md`, `CLAUDE.md` 간단히 언급

### 팁

- `LINK_PATTERN`은 최대한 정확하게 (오탐 방지).
- `CONTENT_CANDIDATES`는 큰 텍스트 블록 순으로.
- `_get_title` override가 필요하면 `<h1>`이나 특정 메타를 사용할 수 있음.
- 항상 `limit` 테스트 + 실제 프리뷰 확인.
- 이미지 포함 여부는 사용자 설정에 위임 (`include_images`).

---

## 5. 기술적 세부 사항

### 파일 의존 관계

```
BaseNewsletterScraper (newsletter_base.py)
    ↑
    └── SoonsalScraper (soonsal.py)

ScraperFactory.get_scraper("soonsal")
    → SyncService / preview / sync_pipeline
    → EpubBuilder
```

### 주요 헬퍼 재사용

- `fetch_url` (retry + pooling)
- `maybe_strip_images`
- `ensure_article_url`
- `get_logger`

### EPUB 결과 특성

- 한 사이트 설정 = 하루치 여러 뉴스레터를 한 EPUB에 포함
- 제목이 풍부하고 섹션(이모지 포함)이 잘 보존됨
- e-ink 최적화를 위해 이미지 기본 제거

---

## 6. 향후 확장 아이디어

- `newsletter_base`를 더 일반화해서 `list_selector`, `title_fallback_selectors` 등을 config로 받을 수 있게 (advanced users)
- 공통 "뉴스레터" 카테고리 UI (이미지 포함 기본값 true 등)
- 날짜 필터 (오늘자만, 최근 3일)
- 여러 뉴스레터 사이트를 하나의 "Daily Briefing"으로 합치는 기능

---

## 7. 검증 체크리스트 (AI 작업 시)

- [ ] `python -c "from websync.scrapers.factory import ...; s=...; s.fetch_articles({...})"` 로 최소 1건 수집 확인
- [ ] `pytest tests/test_scraper_factory.py tests/test_config_validator.py`
- [ ] 전체 `pytest`
- [ ] GUI에서 타입 선택 → CSS 필드 비활성화 확인
- [ ] 프리뷰 + 실제 EPUB 생성 + 내용 확인
- [ ] `docs/` 아래 문서 업데이트
- [ ] `x3_websync.spec` hiddenimport 추가

---

**이 문서는 CLAUDE.md, docs/USER_GUIDE.md 등과 함께 AI가 프로젝트를 이해할 때 가장 먼저 참조해야 할 자료 중 하나다.**

추가 질문이나 다른 뉴스레터 사이트 구현 요청은 언제든 환영.
