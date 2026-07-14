import os
import re
import mimetypes
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional


def normalize_device_host(value: str | None) -> str:
    """기기 주소 정규화: 스킴·경로·끝 슬래시 제거.

    예: 'http://192.168.31.54/' → '192.168.31.54'
    끝 슬래시가 남으면 업로드 URL이 http://IP//upload 가 되어 CrossPoint가 404를 반환한다.
    """
    if value is None:
        return ""
    host = str(value).strip()
    if not host:
        return ""
    # http(s):// 접두 제거
    host = re.sub(r"^https?://", "", host, flags=re.IGNORECASE)
    # 경로/쿼리/프래그먼트 제거 (호스트:포트만 유지)
    host = host.split("/", 1)[0]
    host = host.split("?", 1)[0]
    host = host.split("#", 1)[0]
    return host.strip().rstrip(".")


class X3Uploader:
    """Xteink X3 기기와의 HTTP 업로드 통신을 전담하는 클래스 (단일/다중 기기 지원)"""

    def __init__(self, x3_ip: str, devices: Optional[list] = None):
        self.x3_ip = normalize_device_host(x3_ip)
        self.devices = devices or []
        # 최근 전송 실패 사유 {ip: message} — GUI/파이프라인 로그용
        self.last_errors: dict[str, str] = {}

    def _sanitize_filename(self, file_path: str) -> str:
        """CrossPoint 오작동(공백/특수문자/한글 파일명 크래시) 우회용 파일명 클렌징"""
        base, ext = os.path.splitext(os.path.basename(file_path))
        safe_base = "".join([c if c.isalnum() or c in ("-", "_") else "_" for c in base])
        while "__" in safe_base:
            safe_base = safe_base.replace("__", "_")
        safe_base = safe_base.strip("_")
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
        host = normalize_device_host(ip)
        if not host:
            msg = "기기 주소가 비어 있습니다."
            self.last_errors[str(ip)] = msg
            print(f"❌ [{ip}] {msg}")
            return False

        url = f"http://{host}/upload"
        mime = self._guess_mime(file_path)
        try:
            with open(file_path, "rb") as f:
                files = {"file": (safe_filename, f, mime)}
                response = requests.post(url, files=files, timeout=timeout)
            if response.status_code == 200:
                self.last_errors.pop(host, None)
                return True
            body = (response.text or "").strip().replace("\n", " ")
            if len(body) > 160:
                body = body[:160] + "…"
            msg = f"HTTP {response.status_code}"
            if body:
                msg += f" — {body}"
            if response.status_code == 404 and "//" in url:
                msg += " (주소 끝 '/' 확인)"
            self.last_errors[host] = msg
            print(f"❌ [{host}] 전송 응답 오류: {msg} (URL: {url})")
            return False
        except requests.Timeout as e:
            msg = f"타임아웃 {timeout}초: {e}"
            self.last_errors[host] = msg
            print(f"❌ [{host}] 전송 실패 ({msg})")
            return False
        except Exception as e:
            msg = f"{type(e).__name__}: {e}"
            self.last_errors[host] = msg
            print(f"❌ [{host}] 전송 실패: {msg}")
            return False

    def _build_target_list(self) -> list[dict]:
        """전송 대상 기기 목록 (기본 기기 + x3_devices, 중복 IP 제거)"""
        targets: list[dict] = []
        seen_ips: set[str] = set()

        if self.x3_ip:
            ip = normalize_device_host(self.x3_ip)
            if ip:
                targets.append({"name": "기본 기기", "ip": ip})
                seen_ips.add(ip)

        for dev in self.devices:
            ip = normalize_device_host(dev.get("ip") or "")
            if not ip or ip in seen_ips:
                continue
            targets.append({"name": dev.get("name") or ip, "ip": ip})
            seen_ips.add(ip)

        return targets

    def upload(self, file_path: str) -> bool:
        """메인 기기(x3_ip)로 파일 전송"""
        host = normalize_device_host(self.x3_ip)
        if not host:
            return False
        safe_filename = self._sanitize_filename(file_path)
        timeout = self._calc_timeout(file_path)
        result = self._upload_to_ip(file_path, host, safe_filename, timeout)
        if not result:
            print("💡 팁: CrossPoint 기기가 켜져 있고 Wi-Fi에 연결되어 있는지 확인해 주세요.")
            print("💡 주소에 끝 슬래시(/)나 http:// 를 넣지 마세요. 예: 192.168.31.54")
        return result

    def upload_to_all_devices(self, file_path: str) -> dict:
        """등록된 모든 기기에 병렬로 파일 전송. 결과를 {ip: bool} 로 반환."""
        return self.upload_to_targets(file_path)

    def upload_to_targets(
        self,
        file_path: str,
        only_ips: Optional[list[str]] = None,
    ) -> dict[str, bool]:
        """
        기본 기기 및 x3_devices에 전송합니다.
        반환: {ip: 성공여부} — 키는 항상 기기 IP/호스트입니다.

        only_ips: 지정 시 해당 IP만 전송 (부분 재시도용).
        """
        self.last_errors = {}
        all_devices = self._build_target_list()
        if only_ips is not None:
            allow = {normalize_device_host(ip) for ip in only_ips if normalize_device_host(ip)}
            all_devices = [d for d in all_devices if d["ip"] in allow]

        if not all_devices:
            print("⚠️ 등록된 기기가 없습니다." if only_ips is None else "⚠️ 전송 대상 기기가 없습니다.")
            return {}

        safe_filename = self._sanitize_filename(file_path)
        timeout = self._calc_timeout(file_path)
        results: dict[str, bool] = {}

        with ThreadPoolExecutor(max_workers=min(len(all_devices), 4)) as executor:
            future_to_device = {
                executor.submit(self._upload_to_ip, file_path, d["ip"], safe_filename, timeout): d
                for d in all_devices
            }
            for future in as_completed(future_to_device):
                device = future_to_device[future]
                ip = device["ip"]
                try:
                    results[ip] = future.result()
                except Exception as e:
                    msg = f"{type(e).__name__}: {e}"
                    self.last_errors[ip] = msg
                    print(f"❌ [{device.get('name', ip)}] 전송 예외: {e}")
                    results[ip] = False
        return results

    def test_connection(self, ip: str = None) -> bool:
        """기기가 켜져 있고 지정한 IP/호스트의 웹서버에 접속 가능한지 검사"""
        target_ip = normalize_device_host(ip or self.x3_ip)
        if not target_ip:
            return False
        url = f"http://{target_ip}/"
        try:
            requests.get(url, timeout=3)
            return True
        except Exception:
            return False
