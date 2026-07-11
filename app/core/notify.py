import shutil
import subprocess


def notify(title, message=""):
    """Best-effort desktop notification. Never raises."""
    if shutil.which("notify-send") is None:
        return
    try:
        subprocess.Popen(["notify-send", title, message])
    except Exception:
        pass
