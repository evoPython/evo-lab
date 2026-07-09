import shutil
import subprocess


class ActionError(Exception):
    """Raised when a system action can't be carried out."""


def _run_detached(cmd):
    """
    Fire-and-forget a system command without shell=True, so no
    user-controlled input ever passes through a shell.
    """

    if shutil.which(cmd[0]) is None:
        raise ActionError(f"Command not found on this system: {cmd[0]}")

    subprocess.Popen(cmd)

def lock_screen():
    """
    Lock screen using Noctalia v5.

    Designed for:
    - niri
    - Wayland
    - Noctalia Shell v5

    Requires:
    - noctalia running
    """

    cmd = [
        "noctalia",
        "msg",
        "session",
        "lock",
    ]

    if not shutil.which("noctalia"):
        raise ActionError(
            "Noctalia command not found."
        )

    try:
        subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    except Exception as e:
        raise ActionError(
            f"Failed to lock screen: {e}"
        )

def shutdown():
    # Relies on systemd-logind/polkit allowing the active local user
    # to power off without a password, which is the default on most
    # single-user Arch installs. If it isn't, this will just fail and
    # report the error back to the caller.
    _run_detached(["systemctl", "poweroff"])


def restart():
    _run_detached(["systemctl", "reboot"])


def suspend():
    _run_detached(["systemctl", "suspend"])
