import re
import shutil
import subprocess

SINK = "@DEFAULT_AUDIO_SINK@"


class VolumeError(Exception):
    pass


def _wpctl(*args):
    if shutil.which("wpctl") is None:
        raise VolumeError("wpctl not found (needs PipeWire)")
    try:
        result = subprocess.run(["wpctl", *args], capture_output=True, text=True, timeout=5)
    except Exception as exc:
        raise VolumeError(str(exc))
    if result.returncode != 0:
        raise VolumeError(result.stderr.strip() or "wpctl failed")
    return result.stdout.strip()


def get_status():
    out = _wpctl("get-volume", SINK)
    match = re.search(r"([\d.]+)", out)
    percent = round(float(match.group(1)) * 100) if match else None
    return {"percent": percent, "muted": "MUTED" in out}


def volume_up():
    _wpctl("set-volume", SINK, "5%+")


def volume_down():
    _wpctl("set-volume", SINK, "5%-")


def toggle_mute():
    _wpctl("set-mute", SINK, "toggle")
