import shutil
import subprocess
import time

HOTSPOT_CON_NAME = "Hotspot"


class NMError(Exception):
    pass


def _nmcli(*args, timeout=15):
    if shutil.which("nmcli") is None:
        raise NMError("nmcli not found (needs NetworkManager)")
    try:
        result = subprocess.run(
            ["nmcli", *args], capture_output=True, text=True, timeout=timeout
        )
    except Exception as exc:
        raise NMError(str(exc))
    if result.returncode != 0:
        raise NMError((result.stderr or result.stdout).strip() or "nmcli failed")
    return result.stdout.strip()


def get_wifi_device():
    out = _nmcli("-t", "-f", "DEVICE,TYPE", "device", "status")
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) >= 2 and parts[1] == "wifi":
            return parts[0]
    raise NMError("No wifi device found")


def check_connectivity():
    """Returns one of: full, limited, portal, none, unknown."""
    try:
        return _nmcli("networking", "connectivity", "check", timeout=10)
    except NMError:
        return "unknown"


def get_status():
    device = None
    try:
        device = get_wifi_device()
    except NMError:
        pass

    active_ssid = None
    is_hotspot = False
    ip4 = None

    if device:
        out = _nmcli("-t", "-f", "DEVICE,TYPE,STATE,CONNECTION", "device", "status")
        for line in out.splitlines():
            parts = line.split(":")
            if len(parts) >= 4 and parts[0] == device:
                active_ssid = parts[3] or None
                is_hotspot = active_ssid == HOTSPOT_CON_NAME
        if active_ssid:
            try:
                ip4 = _nmcli(
                    "-t", "-f", "IP4.ADDRESS", "device", "show", device
                ).split(":")[-1].split("/")[0] or None
            except NMError:
                pass

    return {
        "device": device,
        "active_connection": active_ssid,
        "is_hotspot": is_hotspot,
        "ip4": ip4,
        "connectivity": check_connectivity(),
    }


def scan_networks():
    device = get_wifi_device()
    try:
        _nmcli("device", "wifi", "rescan", "ifname", device, timeout=10)
    except NMError:
        pass  # rescan can fail if one just ran recently; the list below still works
    out = _nmcli(
        "-t", "-f", "SSID,SIGNAL,SECURITY,IN-USE", "device", "wifi", "list",
        "ifname", device,
    )
    networks = []
    seen = set()
    for line in out.splitlines():
        parts = line.split(":")
        if len(parts) < 4:
            continue
        ssid, signal, security, in_use = parts[0], parts[1], parts[2], parts[3]
        if not ssid or ssid in seen:
            continue
        seen.add(ssid)
        networks.append({
            "ssid": ssid,
            "signal": int(signal) if signal.isdigit() else 0,
            "secure": bool(security),
            "in_use": in_use == "*",
        })
    networks.sort(key=lambda n: n["signal"], reverse=True)
    return networks


def connect(ssid, password=None):
    device = get_wifi_device()
    args = ["device", "wifi", "connect", ssid, "ifname", device]
    if password:
        args += ["password", password]
    _nmcli(*args, timeout=30)


def disconnect():
    device = get_wifi_device()
    _nmcli("device", "disconnect", device)


def hotspot_up(ssid=None):
    """
    Bring up the hotspot. Assumes the `Hotspot` connection profile already
    exists (created once, manually, as an open network with no password) —
    this just activates it, same as `nmcli connection up Hotspot`. No
    creating, deleting, or modifying the profile; `ssid` is accepted for
    call-site compatibility but unused, since the profile already has its
    SSID baked in.
    """
    _nmcli("connection", "up", HOTSPOT_CON_NAME, timeout=30)


def hotspot_down():
    try:
        _nmcli("connection", "down", HOTSPOT_CON_NAME)
    except NMError:
        pass


def get_hotspot_ssid():
    """
    The SSID actually configured on the Hotspot profile itself — not a
    separately hardcoded guess. Those can drift out of sync (as happened
    when the profile's real SSID was changed but a constant elsewhere
    still said the old one), so always read it straight from nmcli.
    """
    try:
        return _nmcli("-g", "802-11-wireless.ssid", "connection", "show", HOTSPOT_CON_NAME) or None
    except NMError:
        return None


def connect_by_profile(name):
    """Activate a saved connection profile directly by name (`nmcli connection up <name>`)."""
    _nmcli("connection", "up", name, timeout=15)


def reconnect_priority(hotspot_ssid, priority_ssid=None, priority_password=None,
                        wait_seconds=8, poll_interval=1):
    """
    Drop the hotspot and try to get back onto a real network.

    If priority_ssid is given, actively (re)connect to it rather than just
    hoping NetworkManager's autoconnect fires on its own — autoconnect can
    take longer than this wait window, or may simply not trigger the moment
    the radio frees up. Polls status afterward instead of one blind sleep so
    it returns as soon as the connection is actually up.

    If that hasn't landed by the halfway point, also try activating the
    saved connection profile directly (`nmcli connection up <priority_ssid>`)
    as a second approach — sometimes that succeeds even when the direct
    wifi-connect call above didn't.

    If nothing usable came up by the end of the wait, restores the hotspot
    so LAN access to this device isn't left broken. Returns the status dict.
    """
    hotspot_down()

    if priority_ssid:
        try:
            connect(priority_ssid, priority_password)
        except NMError:
            pass  # fall through to the poll loop / hotspot fallback below

    status = get_status()
    waited = 0
    tried_profile_up = False
    while waited < wait_seconds and (not status["active_connection"] or status["is_hotspot"]):
        time.sleep(poll_interval)
        waited += poll_interval
        status = get_status()

        if (priority_ssid and not tried_profile_up and waited >= wait_seconds / 2
                and (not status["active_connection"] or status["is_hotspot"])):
            tried_profile_up = True
            try:
                connect_by_profile(priority_ssid)
            except NMError:
                pass
            status = get_status()

    if not status["active_connection"] or status["is_hotspot"]:
        hotspot_up(hotspot_ssid)
        status = get_status()

    return status
