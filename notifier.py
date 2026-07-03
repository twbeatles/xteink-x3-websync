import subprocess

class ToastNotifier:
    """추가 패키지 설치 없이 Windows PowerShell을 호출하여 토스트(Balloon) 알림을 생성하는 클래스"""
    @staticmethod
    def show_toast(title: str, text: str, is_error: bool = False):
        icon = "Error" if is_error else "Info"
        # PowerShell COM Object를 활용한 무설치 네이티브 토스트 스크립트
        ps_cmd = f"""
        [void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms");
        $obj = New-Object System.Windows.Forms.NotifyIcon;
        $obj.Icon = [System.Drawing.SystemIcons]::Information;
        $obj.BalloonTipIcon = "{icon}";
        $obj.BalloonTipTitle = "{title}";
        $obj.BalloonTipText = "{text}";
        $obj.Visible = $True;
        $obj.ShowBalloonTip(5000);
        """
        try:
            # 백그라운드로 실행하여 파이썬 메인 쓰레드 블로킹 방지
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_cmd],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            print(f"⚠️ 시스템 알림 표시 실패: {e}")
