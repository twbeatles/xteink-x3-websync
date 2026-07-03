import os
import sys
import subprocess

class SchedulerManager:
    """윈도우 작업 스케줄러(schtasks) 등록 및 제어를 전담하는 클래스"""
    TASK_NAME = "XteinkX3WebSyncTask"

    def __init__(self, script_path: str = None):
        if script_path is None:
            self.script_path = os.path.abspath(sys.argv[0])
        else:
            self.script_path = os.path.abspath(script_path)
        self.project_dir = os.path.dirname(self.script_path)

    def register_daily_task(self, hour: str, minute: str) -> bool:
        # 1. 쉘 인젝션 방어용 입력 화이트리스트 정수 검증
        if not hour.isdigit() or not minute.isdigit():
            print("❌ 오류: 스케줄러 시간 인자는 숫자여야 합니다.")
            return False
            
        h_val, m_val = int(hour), int(minute)
        if not (0 <= h_val <= 23) or not (0 <= m_val <= 59):
            print("❌ 오류: 지정한 시간 범주(00-23시 / 00-59분)가 올바르지 않습니다.")
            return False

        python_exe = sys.executable
        # 콘솔창 없이 백그라운드 동작을 위해 pythonw.exe 유도
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = python_exe

        # 2. 작업 스케줄러 기동 시 작업 경로 상실 문제 해결:
        # cmd.exe를 활용해 cd /d로 프로젝트 디렉토리에 우선 진입한 후 pythonw를 실행하도록 조립
        cmd_target = f'cmd.exe /c "cd /d {self.project_dir} && \\"{pythonw_exe}\\" \\"{self.script_path}\\" --sync"'
        
        # 3. 쉘 인젝션을 방지하기 위해 shell=False 형태로 인자 리스트 실행
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

    def unregister_task(self) -> bool:
        cmd = ["schtasks", "/delete", "/tn", self.TASK_NAME, "/f"]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
            return result.returncode == 0
        except Exception as e:
            print(f"스케줄 해제 오류: {e}")
            return False

    def get_task_status(self) -> str:
        """스케줄 작업이 등록되어 있는지 상태 문자열 반환"""
        cmd = ["schtasks", "/query", "/tn", self.TASK_NAME, "/fo", "csv"]
        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
            if result.returncode == 0:
                return "등록됨 (대기 중)"
            else:
                return "등록되지 않음"
        except Exception:
            return "상태 확인 불가"

