import json
import subprocess
import time
from pathlib import Path

from flask import current_app

from app.core.notify import notify


MODES = ("server_first", "normal", "performance")

_ALLOWED_GOVERNORS = {
    "performance", "powersave", "schedutil", "ondemand", "conservative", "userspace",
}

DEFAULTS = {
    # Where the current mode is persisted, so it survives a restart of
    # the app (systemd will happily bounce this process; the mode
    # shouldn't reset to "normal" every time it does).
    "MODE_STATE_FILE": "instance/mode_state.json",

    # systemd --user units that make up "the server" — whatever you
    # actually self-host (site, media stuff, docker compose wrapper
    # unit, etc). Stopped in performance mode, (re)started in
    # server_first/normal. Empty by default until you fill this in.
    "MODE_SERVER_UNITS": [],

    # The tiny "sorry for the interruption" placeholder, started only
    # while in performance mode. See system/just-system-maintenance.service.
    "MODE_MAINTENANCE_UNIT": "just-system-maintenance.service",

    # Process name patterns (matched with `pkill -f`) to close when
    # switching to server_first. Leave empty until you've decided what's
    # safe to kill — this runs as whatever user the app runs as, so it
    # can only close things that user owns anyway.
    "MODE_CLOSE_PROCESSES": [
        "zen",
        "nautilus",
        "nvim",
        "btop",
        "discord",
        "chrome",
        "firefox"
    ],

    # Battery charge thresholds. Written straight to
    # /sys/class/power_supply/BAT*/charge_control_end_threshold via the
    # js-battery-limit helper (asus-nb-wmi exposes this natively on most
    # ASUS laptops — no asusctl needed). Set to None to skip.
    "MODE_BATTERY_LIMIT_SERVER_FIRST": 60,
    "MODE_BATTERY_LIMIT_NORMAL": 100,
    "MODE_BATTERY_LIMIT_PERFORMANCE": 100,

    # CPU governors per mode. Set to None to skip.
    "MODE_CPU_GOVERNOR_SERVER_FIRST": "powersave",
    "MODE_CPU_GOVERNOR_NORMAL": "schedutil",
    "MODE_CPU_GOVERNOR_PERFORMANCE": "performance",

    # Extra raw shell commands (lists of argv lists) to run per mode,
    # for anything hardware/setup-specific (TLP, powertop --auto-tune,
    # a compositor animation toggle, whatever). Each entry is passed
    # straight to subprocess.run, no shell involved.
    "MODE_EXTRA_SERVER_FIRST_CMDS": [],
    "MODE_EXTRA_NORMAL_CMDS": [],
    "MODE_EXTRA_PERFORMANCE_CMDS": [],
}


def _cfg(key):
    return current_app.config.get(key, DEFAULTS[key])


def _state_path():
    path = Path(_cfg("MODE_STATE_FILE"))
    if not path.is_absolute():
        path = Path(current_app.root_path).parent / path
    return path


def get_mode():
    path = _state_path()
    if not path.exists():
        return "normal"
    try:
        data = json.loads(path.read_text())
        mode = data.get("mode")
        return mode if mode in MODES else "normal"
    except (OSError, ValueError):
        return "normal"


def get_mode_changed_at():
    path = _state_path()
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        return data.get("changed_at")
    except (OSError, ValueError):
        return None


def _save_mode(mode):
    path = _state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"mode": mode, "changed_at": time.time()}))


def _run(cmd, warnings):
    """Best-effort subprocess call. Never raises — appends a short
    warning string instead, so one broken step (e.g. sudoers not set
    up yet) doesn't stop the rest of the mode switch from applying."""
    try:
        subprocess.run(cmd, check=True, timeout=15, capture_output=True)
    except Exception as e:
        warnings.append(f"{' '.join(cmd)}: {e}")


def _set_battery_limit(percent, warnings):
    if percent is None:
        return
    percent = max(0, min(100, int(percent)))
    _run(["sudo", "-n", "/usr/local/bin/js-battery-limit", str(percent)], warnings)


def _set_cpu_governor(governor, warnings):
    if governor is None:
        return
    if governor not in _ALLOWED_GOVERNORS:
        warnings.append(f"refusing unknown governor: {governor}")
        return
    _run(["sudo", "-n", "/usr/local/bin/js-cpu-governor", governor], warnings)


def _run_extra(cmds, warnings):
    for cmd in cmds:
        _run(list(cmd), warnings)


def _stop_server_units(warnings):
    for unit in _cfg("MODE_SERVER_UNITS"):
        _run(["systemctl", "--user", "stop", unit], warnings)


def _start_server_units(warnings):
    for unit in _cfg("MODE_SERVER_UNITS"):
        _run(["systemctl", "--user", "start", unit], warnings)


def _stop_maintenance(warnings):
    _run(["systemctl", "--user", "stop", _cfg("MODE_MAINTENANCE_UNIT")], warnings)


def _start_maintenance(warnings):
    _run(["systemctl", "--user", "start", _cfg("MODE_MAINTENANCE_UNIT")], warnings)


def _close_unnecessary_processes(warnings):
    for pattern in _cfg("MODE_CLOSE_PROCESSES"):
        # pkill returns non-zero when nothing matched — that's not a
        # real error, so don't let it surface as a warning.
        subprocess.run(["pkill", "-f", pattern], capture_output=True, timeout=10)


def _apply_server_first(warnings):
    _run(["niri", "msg", "action", "power-off-monitors"], warnings)
    _close_unnecessary_processes(warnings)
    _set_battery_limit(_cfg("MODE_BATTERY_LIMIT_SERVER_FIRST"), warnings)
    _set_cpu_governor(_cfg("MODE_CPU_GOVERNOR_SERVER_FIRST"), warnings)
    _start_server_units(warnings)
    _stop_maintenance(warnings)
    _run_extra(_cfg("MODE_EXTRA_SERVER_FIRST_CMDS"), warnings)


def _apply_normal(warnings):
    _run(["niri", "msg", "action", "power-on-monitors"], warnings)
    _set_battery_limit(_cfg("MODE_BATTERY_LIMIT_NORMAL"), warnings)
    _set_cpu_governor(_cfg("MODE_CPU_GOVERNOR_NORMAL"), warnings)
    _start_server_units(warnings)
    _stop_maintenance(warnings)
    _run_extra(_cfg("MODE_EXTRA_NORMAL_CMDS"), warnings)


def _apply_performance(warnings):
    _run(["niri", "msg", "action", "power-on-monitors"], warnings)
    _set_battery_limit(_cfg("MODE_BATTERY_LIMIT_PERFORMANCE"), warnings)
    _set_cpu_governor(_cfg("MODE_CPU_GOVERNOR_PERFORMANCE"), warnings)
    _stop_server_units(warnings)
    _start_maintenance(warnings)
    _run_extra(_cfg("MODE_EXTRA_PERFORMANCE_CMDS"), warnings)


_APPLIERS = {
    "server_first": _apply_server_first,
    "normal": _apply_normal,
    "performance": _apply_performance,
}


def set_mode(mode):
    if mode not in MODES:
        raise ValueError(f"unknown mode: {mode}")

    warnings = []
    _APPLIERS[mode](warnings)
    _save_mode(mode)
    notify("Mode switched", mode.replace("_", "-"))
    return warnings
