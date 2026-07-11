import os
import re
import shlex
import subprocess

from xdg.DesktopEntry import DesktopEntry

APP_DIRS = [
    "/usr/share/applications",
    os.path.expanduser("~/.local/share/applications"),
]

FIELD_CODE_RE = re.compile(r"%[fFuUick]")


def list_apps():
    apps = {}
    for directory in APP_DIRS:
        if not os.path.isdir(directory):
            continue
        for name in os.listdir(directory):
            if not name.endswith(".desktop"):
                continue
            path = os.path.join(directory, name)
            try:
                entry = DesktopEntry(path)
            except Exception:
                continue
            if entry.getHidden() or entry.getNoDisplay() or not entry.getExec():
                continue
            apps[name] = {
                "id": name,
                "name": entry.getName() or name,
                "exec": entry.getExec(),
            }
    return sorted(apps.values(), key=lambda a: a["name"].lower())


def launch(app_id):
    safe_id = os.path.basename(app_id or "")
    for directory in APP_DIRS:
        path = os.path.join(directory, safe_id)
        if os.path.isfile(path) and safe_id.endswith(".desktop"):
            entry = DesktopEntry(path)
            exec_line = FIELD_CODE_RE.sub("", entry.getExec()).strip()
            args = shlex.split(exec_line)
            if not args:
                raise ValueError("Empty Exec line")
            subprocess.Popen(args, start_new_session=True)
            return entry.getName() or safe_id
    raise ValueError("App not found")
