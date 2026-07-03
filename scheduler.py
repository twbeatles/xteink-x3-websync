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

    def register_daily_task(self, hour: str, minute: str) -> bool:
        python_exe = sys.executable
        # 콘솔창 없이 백그라운드 동작을 위해 pythonw.exe 유도
        pythonw_exe = python_exe.replace("python.exe", "pythonw.exe")
        if not os.path.exists(pythonw_exe):
            pythonw_exe = python_exe

        cmd_target = f'"{pythonw_exe}" "{self.script_path}" --sync'
        cmd = f'schtasks /create /tn "{self.TASK_NAME}" /tr "{cmd_target}" /sc daily /st {hour}:{minute} /f'
        
        try:
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
            return result.returncode == 0
        except Exception as e:
            print(f"스케줄 등록 오류: {e}")
            return False

    def unregister_task(self) -> bool:
        cmd = f'schtasks /delete /tn "{self.TASK_NAME}" /f'
        try:
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
            return result.returncode == 0
        except Exception as e:
            print(f"스케줄 해제 오류: {e}")
            return False

    def get_task_status(self) -> str:
        """스케줄 작업이 등록되어 있는지 상태 문자열 반환"""
        cmd = f'schtasks /query /tn "{self.TASK_NAME}" /fo csv'
        try:
            result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="cp949", errors="ignore")
            if result.returncode == 0:
                return "등록됨 (대기 중)"
            else:
                return "등록되지 않음"
        except Exception:
            return "상태 확인 불가"
