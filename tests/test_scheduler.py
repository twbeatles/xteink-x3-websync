import shlex
import sys
from unittest.mock import patch, MagicMock

from websync.scheduler.manager import SchedulerManager

# Windows 스타일 경로 — GitHub Actions(ubuntu)에서도 호스트 OS와 무관하게 동일하게 동작해야 함
_WIN_SCRIPT = r"C:\Users\First Last\x3\x3_websync.py"
_WIN_PROJECT = r"C:\Users\First Last\x3"
_WIN_PYTHON = r"C:\Program Files\Python\python.exe"
_WIN_PYTHONW = r"C:\Program Files\Python\pythonw.exe"


def test_resolve_script_path_preserves_windows_abs_on_any_host():
    """POSIX abspath가 C:\\… 를 CWD 상대경로로 붙이지 않도록 한다 (CI 재발 방지)."""
    resolved = SchedulerManager._resolve_script_path(_WIN_SCRIPT)
    assert resolved == _WIN_SCRIPT
    assert not resolved.startswith("/")  # Linux CWD 접두 금지
    assert SchedulerManager._dirname_for_script(resolved) == _WIN_PROJECT


def test_linux_cron_quotes_paths_with_spaces():
    mgr = SchedulerManager(script_path="/tmp/my project/x3_websync.py")
    mgr.project_dir = "/tmp/my project"

    with patch.object(mgr, "_register_windows"):
        with patch("sys.platform", "linux"):
            with patch("subprocess.run") as mock_run:
                mock_run.return_value = MagicMock(returncode=0)
                mgr.register_daily_task("07", "30")

    cron_input = mock_run.call_args_list[-1].kwargs.get("input", "")
    assert shlex.quote(mgr.project_dir) in cron_input
    assert shlex.quote(mgr.script_path) in cron_input


def test_windows_tr_command_quotes_paths_with_spaces():
    """공백 포함 Windows 경로를 schtasks /tr 문자열에서 따옴표로 감싼다 (Linux CI 포함)."""
    mgr = SchedulerManager(script_path=_WIN_SCRIPT)
    assert mgr.script_path == _WIN_SCRIPT
    assert mgr.project_dir == _WIN_PROJECT
    with patch.object(sys, "executable", _WIN_PYTHON):
        with patch("os.path.exists", return_value=True):
            tr = mgr.build_windows_tr_command()
    assert f'cd /d "{_WIN_PROJECT}"' in tr
    assert f'"{_WIN_SCRIPT}"' in tr
    assert f'"{_WIN_PYTHONW}"' in tr
    assert "--sync" in tr
    # POSIX abspath가 CWD를 Windows 경로 앞에 붙인 회귀 차단
    assert tr.count(_WIN_SCRIPT) == 1


def test_macos_unloads_before_load():
    mgr = SchedulerManager(script_path="/tmp/x3_websync.py")

    with patch("sys.platform", "darwin"):
        with patch("os.path.expanduser", return_value="/tmp/LaunchAgents"):
            with patch("os.makedirs"):
                with patch("os.path.exists", return_value=True):
                    with patch("subprocess.run") as mock_run:
                        mock_run.return_value = MagicMock(returncode=0)
                        with patch("builtins.open", MagicMock()):
                            mgr.register_daily_task("08", "00")

    calls = [c.args[0] for c in mock_run.call_args_list if c.args]
    assert ["launchctl", "unload"] in [c[:2] for c in calls]
    assert ["launchctl", "load"] in [c[:2] for c in calls]