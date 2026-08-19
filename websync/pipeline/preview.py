"""프리뷰(스크래핑만) 파이프라인."""
from __future__ import annotations

from typing import Callable, Optional

from websync.scrapers import ScraperFactory
from websync.scrapers.base import is_allowed_fetch_url
from websync.upload.uploader import X3Uploader
from websync.pipeline.article_keys import article_sync_key

def preview_articles(
    service,
    log_callback: Optional[Callable[[str], None]] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None
) -> list[dict]:
    """
    기사를 스크래핑하고 필터링하지만 EPUB 빌드 및 업로드는 생략하고 결과를 반환합니다.
    
    Returns:
        [{"site_name": str, "title": str, "url": str, "content": str, "scraper_type": str}]
    """
    def log(msg: str):
        service.logger.info(msg)
        if log_callback:
            log_callback(msg)
        else:
            print(msg)

    # 파이프라인과 동일 락을 비차단 획득 (N7 — service 헬퍼로 통일)
    if not service._try_acquire_pipeline_locks(log):
        log("⚠️ 이미 파이프라인이 구동 중이거나 다른 프로세스에서 동기화 중이므로 프리뷰를 실행할 수 없습니다.")
        return []

    try:
        # 공유 데이터 폴더 pull — 본 파이프라인과 동일하게 정본 반영 후 최신 config 사용 (N4)
        service.maybe_backup_pull(log_callback=log)
        # config 스냅샷 사용 — 실행 중 service.config 교체로 인한 stale 참조 방지
        config = service.config_manager.load_config()
        enabled_sites = [s for s in config.get("sites", []) if s.get("enabled", True)]
        if not enabled_sites:
            log("⚠️ 활성화된 수집 대상 사이트가 없습니다.")
            return []

        total_sites = len(enabled_sites)
        df = config.get("device_files") or {}
        uploader = X3Uploader(
            x3_ip=config.get("x3_ip", "crosspoint.local"),
            devices=config.get("x3_devices", []),
            remote_dir=df.get("default_upload_path", "/"),
            primary_device_id=config.get("x3_primary_device_id", "") or "",
        )
        upload_targets = uploader._build_target_list()
        from websync.backup.portable_cfg import get_portable_cfg
        from websync.upload.device_ids import alias_key_groups, history_keys_from_targets

        target_history_keys = history_keys_from_targets(upload_targets)
        key_aliases = alias_key_groups(upload_targets)
        history_mode = get_portable_cfg(config).get("history_mode", "per_device")
        preview_results = []

        for site_idx, site in enumerate(enabled_sites):
            name = site.get("name", "무명 사이트")
            scraper_type = site.get("type", "css")
            base_url = site.get("url", "")

            if not is_allowed_fetch_url(base_url):
                log(f"⚠️ [{name}] URL이 http(s)가 아니어서 건너뜁니다: {(base_url or '')[:80]}")
                continue

            if progress_callback:
                progress_callback(site_idx, total_sites)

            log(f"\n[📰 {name}] ({scraper_type.upper()}) 기사 스크래핑(프리뷰) 중...")
            try:
                scraper = ScraperFactory.get_scraper(scraper_type)
                articles = scraper.fetch_articles(site)

                if not articles:
                    log(f"⚠️ [{name}] 수집된 기사가 없습니다.")
                    continue

                for art in articles:
                    art["url"] = article_sync_key(art, name, base_url)

                new_articles = []
                for art in articles:
                    url = art.get("url")
                    if not url:
                        continue
                    if service.db.needs_sync(
                        url,
                        target_history_keys,
                        history_mode=history_mode,
                        key_aliases=key_aliases,
                    ):
                        new_articles.append(art)

                log(f"   => 수집: {len(articles)}건 (신규 검출: {len(new_articles)}건)")
                for art in new_articles:
                    preview_results.append({
                        "site_name": name,
                        "title": art.get("title", "제목 없음"),
                        "url": art.get("url", ""),
                        "content": art.get("content", ""),
                        "scraper_type": scraper_type
                    })
            except Exception as e:
                service.logger.exception(f"[{name}] 프리뷰 중 오류: {e}")
                log(f"❌ [{name}] 스크래핑 실패: {e}")

        if progress_callback:
            progress_callback(total_sites, total_sites)

        log(f"\n📊 프리뷰 요약: 총 {len(preview_results)}개의 신규 기사를 검출했습니다.")
        return preview_results
    finally:
        service._release_pipeline_locks()
