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


def get_windows():
    return _niri_json("windows")


def get_workspaces():
    return _niri_json("workspaces")


def get_outputs():
    return _niri_json("outputs")


def get_overview_state():
    return _niri_json("overview-state")


def get_state():
    return {
        "windows": get_windows(),
        "workspaces": get_workspaces(),
        "outputs": get_outputs(),
        "overview": get_overview_state(),
    }


ALLOWED_ACTIONS = {
    "focus-window",
    "fullscreen-window",
    "move-window-to-workspace",
    "move-column-left",
    "move-column-right",
    "close-window",
    "maximize-column",
    "set-column-width",
}


FOCUS_SENSITIVE = {"move-column-left", "move-column-right", "maximize-column", "set-column-width"}


def _get_focused_window_id():
    for w in _niri_json("windows"):
        if w.get("is_focused"):
            return w["id"]
    return None


def run_action(action, window_id=None, workspace_idx=None, value=None):
    if action not in ALLOWED_ACTIONS:
        raise NiriError(f"Action not allowed: {action}")
    if shutil.which("niri") is None:
        raise NiriError("niri command not found")

    # These actions apply to the currently focused column, not to
    # --id, so temporarily focus the target window, run the action,
    # then restore whatever was focused before.
    original_focus = None
    if action in FOCUS_SENSITIVE and window_id is not None:
        original_focus = _get_focused_window_id()
        if original_focus != int(window_id):
            _run(["niri", "msg", "action", "focus-window", "--id", str(int(window_id))])

    cmd = ["niri", "msg", "action", action]

    if action in ("focus-window", "fullscreen-window", "close-window"):
        cmd += ["--id", str(int(window_id))]
    elif action == "move-window-to-workspace":
        cmd += ["--window-id", str(int(window_id)), str(int(workspace_idx))]
    elif action == "set-column-width":
        if not value:
            raise NiriError("set-column-width requires a value (e.g. '50%')")
        cmd += [str(value)]

    _run(cmd)

    if original_focus is not None and original_focus != int(window_id):
        _run(["niri", "msg", "action", "focus-window", "--id", str(original_focus)])

    return True


def _run(cmd):
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=5)
    except Exception as exc:
        raise NiriError(str(exc))
    if result.returncode != 0:
        raise NiriError(result.stderr.strip() or "niri action failed")
