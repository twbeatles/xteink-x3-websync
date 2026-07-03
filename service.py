import os
from scrapers import ScraperFactory
from builder import EpubBuilder
from uploader import X3Uploader
from notifier import ToastNotifier
from config_manager import ConfigManager
from db_manager import SyncHistoryDb

class SyncService:
    """전체 동기화 비즈니스 로직 조율을 전담하는 클래스"""
    def __init__(self, config_manager: ConfigManager):
        self.config_manager = config_manager
        self.config = self.config_manager.load_config()
        self.db = SyncHistoryDb() # SQLite3 이력 DB 생성
        
        self.epub_builder = EpubBuilder(
            output_dir=self.config.get("output_dir", "./output"),
            font_family=self.config.get("font_family", "serif"),
            font_size=self.config.get("font_size", 16),
            line_height=self.config.get("line_height", 1.7)
        )
        self.uploader = X3Uploader(self.config.get("x3_ip", "crosspoint.local"))

    def run_sync_pipeline(self, log_callback=None) -> bool:
        def log(msg):
            if log_callback:
                log_callback(msg)
            else:
                print(msg)

        log("✨ 동기화 프로세스를 실행합니다...")
        
        # 최신 설정 리로드
        self.config = self.config_manager.load_config()
        self.epub_builder.output_dir = self.config.get("output_dir", "./output")
        self.epub_builder.font_family = self.config.get("font_family", "serif")
        self.epub_builder.font_size = self.config.get("font_size", 16)
        self.epub_builder.line_height = self.config.get("line_height", 1.7)
        self.uploader.x3_ip = self.config.get("x3_ip", "crosspoint.local")

        enabled_sites = [s for s in self.config.get("sites", []) if s.get("enabled", True)]
        if not enabled_sites:
            log("⚠️ 활성화된 수집 대상 사이트가 설정에 없습니다.")
            ToastNotifier.show_toast("X3 WebSync 실패", "동기화가 중단되었습니다. 활성화된 사이트가 없습니다.", is_error=True)
            return False

        success_count = 0
        actual_work_sites = 0 # 새 기사가 있어 실제 전송을 시도한 사이트 개수

        for site in enabled_sites:
            name = site.get("name", "무명 사이트")
            scraper_type = site.get("type", "css")
            
            log(f"\n[📰 {name}] ({scraper_type.upper()}) 글 수집 중...")
            try:
                scraper = ScraperFactory.get_scraper(scraper_type)
                articles = scraper.fetch_articles(site)
                
                if not articles:
                    log(f"⚠️ [{name}] 수집 성공했으나 기사가 비어있어 건너뜁니다.")
                    continue

                # SQLite DB를 조회하여 이미 전송된 글 필터링 (증분 동기화)
                new_articles = []
                for art in articles:
                    art_url = art.get("url") or art.get("title")
                    if not self.db.is_synced(art_url):
                        new_articles.append(art)
                
                if not new_articles:
                    log(f"   => 💡 모든 글({len(articles)}개)이 이미 이전에 전송된 중복 포스트입니다. 전송을 건너뜁니다.")
                    continue

                actual_work_sites += 1
                log(f"📦 [{name}] 신규 포스트 {len(new_articles)}개 검출 (기존 {len(articles) - len(new_articles)}개 스킵). EPUB 문서 제작 중...")
                epub_path = self.epub_builder.build(name, new_articles)
                log(f"   => 파일 생성: {os.path.basename(epub_path)}")

                log(f"📡 기기({self.uploader.x3_ip})로 무선 파일 전송 중...")
                if self.uploader.upload(epub_path):
                    log(f"🎉 [{name}] 동기화 완료 및 전송 성공!")
                    
                    # 성공적으로 업로드 되었으므로 신규 글들을 이력 DB에 완료 기록
                    for art in new_articles:
                        art_url = art.get("url") or art.get("title")
                        self.db.mark_synced(art_url, name, art.get("title"))
                        
                    success_count += 1
                else:
                    log(f"❌ [{name}] 전송 실패! 기기가 켜져 있고 Wi-Fi 상태인지 확인하세요.")
            except Exception as e:
                log(f"❌ [{name}] 처리 중 오류 발생: {e}")

        # 전체 결과 메시지 튜닝
        if actual_work_sites == 0:
            log("\n📊 작업 결과 요약: 모든 등록 사이트에 전송할 신규 포스트가 없습니다. (기기 전송 생략)")
            ToastNotifier.show_toast(
                "X3 WebSync 상태",
                "모든 뉴스 사이트/블로그에 새로 업로드된 신규 기사가 없어 전송을 생략했습니다."
            )
            return True # 새로운 것이 없는 상태의 정상 종료

        log(f"\n📊 작업 결과 요약: {success_count} / {actual_work_sites} 개 신규 소식 사이트 동기화 전송 완료.")
        
        # 동기화 결과에 따라 Windows 토스트 알림 작동
        if success_count > 0:
            ToastNotifier.show_toast(
                "X3 WebSync 동기화 완료",
                f"신규 업데이트된 {success_count}개 사이트 소식이 무선 전송되었습니다."
            )
        else:
            ToastNotifier.show_toast(
                "X3 WebSync 동기화 실패",
                "신규 포스트 전송 과정에 오류가 발생했습니다. (기기 연결 상태 확인 요망)",
                is_error=True
            )
            
        return success_count > 0

