import shlex
import sys
from unittest.mock import patch, MagicMock

from websync.scheduler.manager import SchedulerManager


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
    mgr = SchedulerManager(script_path=r"C:\Users\First Last\x3\x3_websync.py")
    mgr.project_dir = r"C:\Users\First Last\x3"
    with patch.object(sys, "executable", r"C:\Program Files\Python\python.exe"):
        with patch("os.path.exists", return_value=True):
            tr = mgr.build_windows_tr_command()
    assert 'cd /d "C:\\Users\\First Last\\x3"' in tr
    assert '"C:\\Users\\First Last\\x3\\x3_websync.py"' in tr
    assert "--sync" in tr


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