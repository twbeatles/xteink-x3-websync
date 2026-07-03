import subprocess

class ToastNotifier:
    """추가 패키지 설치 없이 Windows PowerShell을 호출하여 토스트(Balloon) 알림을 생성하는 클래스"""
    @staticmethod
    def show_toast(title: str, text: str, is_error: bool = False):
        icon = "Error" if is_error else "Info"
        # 쉘 인젝션 차단: 스크립트 템플릿과 데이터를 분리해 파라미터($args)로 안전하게 주입
        ps_script = (
            '[void] [System.Reflection.Assembly]::LoadWithPartialName("System.Windows.Forms"); '
            '$obj = New-Object System.Windows.Forms.NotifyIcon; '
            '$obj.Icon = [System.Drawing.SystemIcons]::Information; '
            '$obj.BalloonTipIcon = $args[2]; '
            '$obj.BalloonTipTitle = $args[0]; '
            '$obj.BalloonTipText = $args[1]; '
            '$obj.Visible = $True; '
            '$obj.ShowBalloonTip(5000);'
        )
        try:
            # 백그라운드로 실행하며 args를 리스트로 기입해 쉘 주입 원천 봉쇄
            subprocess.Popen(
                ["powershell", "-NoProfile", "-Command", ps_script, title, text, icon],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW
            )
        except Exception as e:
            print(f"⚠️ 시스템 알림 표시 실패: {e}")
