import os
import mimetypes
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

class X3Uploader:
    """Xteink X3 기기와의 HTTP 업로드 통신을 전담하는 클래스 (단일/다중 기기 지원)"""
    def __init__(self, x3_ip: str, devices: Optional[list] = None):
        self.x3_ip = x3_ip
        self.devices = devices or []

    def _sanitize_filename(self, file_path: str) -> str:
        """CrossPoint 오작동(공백/특수문자/한글 파일명 크래시) 우회용 파일명 클렌징"""
        base, ext = os.path.splitext(os.path.basename(file_path))
        safe_base = "".join([c if c.isalnum() or c in ('-', '_') else '_' for c in base])
        while '__' in safe_base:
            safe_base = safe_base.replace('__', '_')
        safe_base = safe_base.strip('_')
        if not safe_base:
            safe_base = "sync_book"
        return safe_base + ext.lower()

    def _guess_mime(self, file_path: str) -> str:
        mime, _ = mimetypes.guess_type(file_path)
        return mime or "application/octet-stream"

    def _calc_timeout(self, file_path: str) -> int:
        """파일 크기 기반 가변 타임아웃 계산"""
        try:
            file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
        except Exception:
            file_size_mb = 1.0
        return int(25 + (file_size_mb * 5))

    def _upload_to_ip(self, file_path: str, ip: str, safe_filename: str, timeout: int) -> bool:
        """지정 IP의 기기로 파일 1건 전송"""
        url = f"http://{ip}/upload"
        mime = self._guess_mime(file_path)
        try:
            with open(file_path, "rb") as f:
                files = {"file": (safe_filename, f, mime)}
                response = requests.post(url, files=files, timeout=timeout)
            if response.status_code == 200:
                return True
            print(f"❌ [{ip}] 전송 응답 오류: HTTP {response.status_code}")
            return False
        except Exception as e:
            print(f"❌ [{ip}] 전송 실패 (타임아웃 {timeout}초): {e}")
            return False

    def _build_target_list(self) -> list[dict]:
        """전송 대상 기기 목록 (기본 기기 + x3_devices, 중복 IP 제거)"""
        targets: list[dict] = []
        seen_ips: set[str] = set()

        if self.x3_ip:
            targets.append({"name": "기본 기기", "ip": self.x3_ip})
            seen_ips.add(self.x3_ip)

        for dev in self.devices:
            ip = (dev.get("ip") or "").strip()
            if not ip or ip in seen_ips:
                continue
            targets.append({"name": dev.get("name", ip), "ip": ip})
            seen_ips.add(ip)

        return targets

    def upload(self, file_path: str) -> bool:
        """메인 기기(x3_ip)로 파일 전송"""
        if not self.x3_ip:
            return False
        safe_filename = self._sanitize_filename(file_path)
        timeout = self._calc_timeout(file_path)
        result = self._upload_to_ip(file_path, self.x3_ip, safe_filename, timeout)
        if not result:
            print("💡 팁: CrossPoint 기기가 켜져 있고 Wi-Fi에 연결되어 있는지 확인해 주세요.")
        return result

    def upload_to_all_devices(self, file_path: str) -> dict:
        """등록된 모든 기기에 병렬로 파일 전송. 결과를 {기기명: bool} 딕셔너리로 반환."""
        return self.upload_to_targets(file_path)

    def upload_to_targets(self, file_path: str) -> dict:
        """기본 기기 및 x3_devices 전체에 단일 경로로 전송합니다."""
        all_devices = self._build_target_list()
        if not all_devices:
            print("⚠️ 등록된 기기가 없습니다.")
            return {}

        safe_filename = self._sanitize_filename(file_path)
        timeout = self._calc_timeout(file_path)
        results = {}

        with ThreadPoolExecutor(max_workers=min(len(all_devices), 4)) as executor:
            future_to_device = {
                executor.submit(self._upload_to_ip, file_path, d["ip"], safe_filename, timeout): d
                for d in all_devices
            }
            for future in as_completed(future_to_device):
                device = future_to_device[future]
                name = device.get("name", device["ip"])
                try:
                    results[name] = future.result()
                except Exception as e:
                    print(f"❌ [{name}] 전송 예외: {e}")
                    results[name] = False
        return results

    def test_connection(self, ip: str = None) -> bool:
        """기기가 켜져 있고 지정한 IP/호스트의 웹서버에 접속 가능한지 검사"""
        target_ip = ip or self.x3_ip
        url = f"http://{target_ip}/"
        try:
            requests.get(url, timeout=3)
            return True
        except Exception:
            return False
