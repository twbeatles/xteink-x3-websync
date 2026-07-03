import os
import sys
import subprocess

class SchedulerManager:
    """작업 스케줄러 등록 및 제어를 전담하는 클래스 (Windows/macOS/Linux 크로스플랫폼 지원)"""
    TASK_NAME = "XteinkX3WebSyncTask"

    def __init__(self, script_path: str = None):
        if script_path is None:
            self.script_path = os.path.abspath(sys.argv[0])
        else:
            self.script_path = os.path.abspath(script_path)
        self.project_dir = os.path.dirname(self.script_path)

    def register_daily_task(self, hour: str, minute: str) -> bool:
        """플랫폼에 맞는 일간 스케줄 등록"""
        # 쉘 인젝션 방어용 입력 화이트리스트 정수 검증
        if not hour.isdigit() or not minute.isdigit():
            print("❌ 오류: 스케줄러 시간 인자는 숫자여야 합니다.")
            return False
        h_val, m_val = int(hour), int(minute)
        if not (0 <= h_val <= 23) or not (0 <= m_val <= 59):
            print("❌ 오류: 지정한 시간 범주(00-23시 / 00-59분)가 올바르지 않습니다.")
            return False

        if sys.platform == "win32":
            return self._register_windows(h_val, m_val)
        elif sys.platform == "darwin":
            return self._register_macos(h_val, m_val)
        else:
            return self._register_linux(h_val, m_val)

    def _register_windows(self, h_val: int, m_val: int) -> bool:
        """Windows schtasks 기반 등록"""
        if getattr(sys, 'frozen', False):
            # PyInstaller 빌드 환경
            cmd_target = f'cmd.exe /c "cd /d {self.project_dir} && \\"{self.script_path}\\" --sync"'
        else:
            python_exe = sys.executable
            pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
            if not os.path.exists(pythonw_exe):
                pythonw_exe = python_exe
            cmd_target = f'cmd.exe /c "cd /d {self.project_dir} && \\"{pythonw_exe}\\" \\"{self.script_path}\\" --sync"'

        cmd = [
            "schtasks", "/create",
            "/tn", self.TASK_NAME,
            "/tr", cmd_target,
            "/sc", "daily",
            "/st", f"{h_val:02d}:{m_val:02d}",
            "/f"
        ]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
            return result.returncode == 0
        except Exception as e:
            print(f"스케줄 등록 오류: {e}")
            return False

    def _register_macos(self, h_val: int, m_val: int) -> bool:
        """macOS launchd plist 기반 등록"""
        plist_dir = os.path.expanduser("~/Library/LaunchAgents")
        os.makedirs(plist_dir, exist_ok=True)
        plist_path = os.path.join(plist_dir, f"com.x3websync.{self.TASK_NAME}.plist")
        python_exe = sys.executable

        if getattr(sys, 'frozen', False):
            args_xml = f"""        <string>{self.script_path}</string>
        <string>--sync</string>"""
        else:
            args_xml = f"""        <string>{python_exe}</string>
        <string>{self.script_path}</string>
        <string>--sync</string>"""

        plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.x3websync.{self.TASK_NAME}</string>
    <key>ProgramArguments</key>
    <array>
{args_xml}
    </array>
    <key>StartCalendarInterval</key>
    <dict>
        <key>Hour</key>
        <integer>{h_val}</integer>
        <key>Minute</key>
        <integer>{m_val}</integer>
    </dict>
    <key>WorkingDirectory</key>
    <string>{self.project_dir}</string>
    <key>StandardOutPath</key>
    <string>{self.project_dir}/logs/launchd_stdout.log</string>
    <key>StandardErrorPath</key>
    <string>{self.project_dir}/logs/launchd_stderr.log</string>
</dict>
</plist>"""
        try:
            with open(plist_path, "w", encoding="utf-8") as f:
                f.write(plist_content)
            # launchctl 로드
            result = subprocess.run(["launchctl", "load", plist_path], capture_output=True)
            return result.returncode == 0
        except Exception as e:
            print(f"macOS 스케줄 등록 오류: {e}")
            return False

    def _register_linux(self, h_val: int, m_val: int) -> bool:
        """Linux crontab 기반 등록"""
        if getattr(sys, 'frozen', False):
            cron_cmd = f"{m_val} {h_val} * * * cd {self.project_dir} && {self.script_path} --sync >> {self.project_dir}/logs/cron.log 2>&1"
        else:
            python_exe = sys.executable
            cron_cmd = f"{m_val} {h_val} * * * cd {self.project_dir} && {python_exe} {self.script_path} --sync >> {self.project_dir}/logs/cron.log 2>&1"
        try:
            # 기존 크론탭 읽기
            result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
            existing = result.stdout if result.returncode == 0 else ""
            # 기존 등록 제거
            lines = [l for l in existing.splitlines() if self.TASK_NAME not in l and self.script_path not in l]
            lines.append(f"# {self.TASK_NAME}")
            lines.append(cron_cmd)
            new_crontab = "\n".join(lines) + "\n"
            proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
            return proc.returncode == 0
        except Exception as e:
            print(f"Linux 크론 등록 오류: {e}")
            return False


    def unregister_task(self) -> bool:
        if sys.platform == "win32":
            cmd = ["schtasks", "/delete", "/tn", self.TASK_NAME, "/f"]
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
                return result.returncode == 0
            except Exception as e:
                print(f"스케줄 해제 오류: {e}")
                return False
        elif sys.platform == "darwin":
            plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.x3websync.{self.TASK_NAME}.plist")
            try:
                subprocess.run(["launchctl", "unload", plist_path], capture_output=True)
                if os.path.exists(plist_path):
                    os.remove(plist_path)
                return True
            except Exception as e:
                print(f"macOS 스케줄 해제 오류: {e}")
                return False
        else:
            try:
                result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
                existing = result.stdout if result.returncode == 0 else ""
                lines = [l for l in existing.splitlines() if self.TASK_NAME not in l and self.script_path not in l]
                new_crontab = "\n".join(lines) + "\n"
                proc = subprocess.run(["crontab", "-"], input=new_crontab, text=True, capture_output=True)
                return proc.returncode == 0
            except Exception as e:
                print(f"Linux 크론 해제 오류: {e}")
                return False

    def get_task_status(self) -> str:
        """스케줄 작업이 등록되어 있는지 상태 문자열 반환"""
        if sys.platform == "win32":
            cmd = ["schtasks", "/query", "/tn", self.TASK_NAME, "/fo", "csv"]
            try:
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
                return "등록됨 (대기 중)" if result.returncode == 0 else "등록되지 않음"
            except Exception:
                return "상태 확인 불가"
        elif sys.platform == "darwin":
            plist_path = os.path.expanduser(f"~/Library/LaunchAgents/com.x3websync.{self.TASK_NAME}.plist")
            return "등록됨 (launchd)" if os.path.exists(plist_path) else "등록되지 않음"
        else:
            try:
                result = subprocess.run(["crontab", "-l"], capture_output=True, text=True)
                return "등록됨 (crontab)" if self.TASK_NAME in result.stdout else "등록되지 않음"
            except Exception:
                return "상태 확인 불가"
