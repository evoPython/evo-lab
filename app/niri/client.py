import json
import shutil
import subprocess


class NiriError(Exception):
    pass


def _niri_json(*args):
    if shutil.which("niri") is None:
        raise NiriError("niri command not found")
    try:
        out = subprocess.run(
            ["niri", "msg", "-j", *args],
            capture_output=True, text=True, timeout=5,
        )
    except Exception as exc:
        raise NiriError(str(exc))
    if out.returncode != 0:
        raise NiriError(out.stderr.strip() or "niri msg failed")
    try:
        return json.loads(out.stdout)
    except json.JSONDecodeError:
        raise NiriError("Could not parse niri output")


def get_state():
    return {
        "windows": _niri_json("windows"),
        "workspaces": _niri_json("workspaces"),
        "outputs": _niri_json("outputs"),
        "overview": _niri_json("overview-state"),
    }


ALLOWED_ACTIONS = {
    "focus-window",
    "fullscreen-window",
    "move-window-to-workspace",
    "move-column-left",
    "move-column-right",
}


def run_action(action, window_id=None, workspace_idx=None):
    if action not in ALLOWED_ACTIONS:
        raise NiriError(f"Action not allowed: {action}")
    if shutil.which("niri") is None:
        raise NiriError("niri command not found")

    cmd = ["niri", "msg", "action", action]

    if action in ("focus-window", "fullscreen-window"):
        cmd += ["--id", str(int(window_id))]
    elif action == "move-window-to-workspace":
        cmd += ["--window-id", str(int(window_id)), str(int(workspace_idx))]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except Exception as exc:
        raise NiriError(str(exc))

    if result.returncode != 0:
        raise NiriError(result.stderr.strip() or "niri action failed")

    return True
