import re
import shutil
import subprocess


class BrightnessError(Exception):
    pass


def _run(*args):
    if shutil.which("brightnessctl") is None:
        raise BrightnessError("brightnessctl not found")
    try:
        result = subprocess.run(["brightnessctl", *args], capture_output=True, text=True, timeout=5)
    except Exception as exc:
        raise BrightnessError(str(exc))
    if result.returncode != 0:
        raise BrightnessError(result.stderr.strip() or "brightnessctl failed")
    return result.stdout.strip()


def get_status():
    out = _run("info")
    match = re.search(r"\((\d+)%\)", out)
    return {"percent": int(match.group(1)) if match else None}


def brightness_up():
    _run("set", "5%+")


def brightness_down():
    _run("set", "5%-")
