import os
import requests

class X3Uploader:
    """Xteink X3 기기와의 HTTP 업로드 통신을 전담하는 클래스"""
    def __init__(self, x3_ip: str):
        # x3_ip는 IP 주소 외에도 crosspoint.local 등의 mDNS 호스트명도 수용
        self.x3_ip = x3_ip

    def upload(self, file_path: str) -> bool:
        url = f"http://{self.x3_ip}/upload"
        
        # 파일 확장자 분리 및 CrossPoint 오작동(공백/특수문자/한글 파일명 크래시) 우회용 파일명 클렌징
        base, ext = os.path.splitext(os.path.basename(file_path))
        # 영숫자, 하이픈(-), 언더바(_)를 제외한 특수문자 및 다국어를 언더바로 일괄 정제
        safe_base = "".join([c if c.isalnum() or c in ('-', '_') else '_' for c in base])
        # 연속된 언더바 정리
        while '__' in safe_base:
            safe_base = safe_base.replace('__', '_')
        safe_base = safe_base.strip('_')
        if not safe_base:
            safe_base = "sync_book"
        safe_file_name = safe_base + ext.lower()

        try:
            with open(file_path, "rb") as f:
                # 안전한 파일명으로 헤더 구성하여 전송
                files = {"file": (safe_file_name, f, "application/epub+zip")}
                response = requests.post(url, files=files, timeout=25)
            
            if response.status_code == 200:
                return True
            else:
                print(f"❌ 전송 응답 오류: HTTP {response.status_code}")
                return False
        except Exception as e:
            print(f"❌ 전송 실패: {e}")
            print("💡 팁: CrossPoint 기기가 켜져 있고 Wi-Fi 또는 충전 케이블에 안정적으로 연결되어 있는지 확인해 주세요.")
            print("    (CrossPoint는 기기가 절전 모드로 진입하면 무선 연결을 자동 차단합니다.)")
            return False

    def test_connection(self) -> bool:
        """기기가 켜져 있고 지정한 IP/호스트의 웹서버에 접속 가능한지 검사"""
        url = f"http://{self.x3_ip}/"
        try:
            response = requests.get(url, timeout=3)
            return True
        except Exception:
            return False
