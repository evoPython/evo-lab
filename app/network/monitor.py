import os
import threading
import time

from app.network import nm

# The only network we hold a known password for, so it always gets first
# dibs when the monitor looks for real internet.
PRIORITY_SSID = os.getenv("EVO_PRIORITY_SSID", "pisay2")
PRIORITY_PASSWORD = os.getenv("EVO_PRIORITY_PASSWORD", "2pisay@philsci24")

HOTSPOT_SSID = os.getenv("EVO_HOTSPOT_SSID", "evo.lostbytes.me")

# Wifi can't scan/associate while it's busy running the AP, so the
# wifi-connected checks below are relatively frequent, but the
# hotspot-mode recheck is deliberately spaced out — every recheck
# means briefly dropping the hotspot, which boots anything connected
# to it over LAN.
POLL_INTERVAL = 5
HOTSPOT_RECHECK_INTERVAL = 120 
FAIL_STREAK_BEFORE_HOTSPOT = 1  # react on the first bad check — the reconnect attempt below is itself the verification step, so no separate debounce buffer is needed

_started = False
_start_lock = threading.Lock()

# Held around any state-changing nmcli call (manual or automatic) so the
# monitor thread and user-triggered actions from routes.py never race.
action_lock = threading.RLock()

auto_enabled = True
last_status = {}


def _try_priority_network():
    """Attempt the one network we have a saved password for. Returns True on full connectivity."""
    try:
        nm.connect(PRIORITY_SSID, PRIORITY_PASSWORD)
    except nm.NMError:
        return False
    time.sleep(3)
    return nm.check_connectivity() == "full"


def _enter_hotspot():
    try:
        nm.hotspot_up(HOTSPOT_SSID)
    except nm.NMError:
        pass


def _sleep_while_auto(seconds, step=1):
    """
    Sleep in small increments, checking auto_enabled each time. If auto
    mode gets turned off mid-wait, this returns right away instead of
    finishing out the rest of whatever recheck interval was already in
    progress — so disabling auto fallback takes effect immediately rather
    than up to HOTSPOT_RECHECK_INTERVAL seconds later.
    """
    slept = 0
    while slept < seconds and auto_enabled:
        time.sleep(step)
        slept += step


def _worker():
    fail_streak = 0
    while True:
        is_hotspot = False
        try:
            if auto_enabled:
                with action_lock:
                    status = nm.get_status()
                    last_status.update(status)
                    is_hotspot = status["is_hotspot"]

                    if is_hotspot:
                        # Occasionally step out of hotspot mode to see if
                        # real internet has come back (e.g. pisay2 in range).
                        nm.hotspot_down()
                        got_internet = _try_priority_network()
                        if not got_internet:
                            _enter_hotspot()
                    else:
                        connectivity = status["connectivity"]
                        if connectivity == "full":
                            fail_streak = 0
                        else:
                            fail_streak += 1
                            if fail_streak >= FAIL_STREAK_BEFORE_HOTSPOT:
                                # No usable internet on whatever we're on (or
                                # nothing at all) — try the known network once,
                                # then fall back to the LAN-only hotspot.
                                if not _try_priority_network():
                                    _enter_hotspot()
                                fail_streak = 0
                # Lock released before the long recheck sleep so a manual
                # button press from the UI isn't blocked out for the whole
                # interval, and so auto_enabled can be checked live.
                if is_hotspot:
                    _sleep_while_auto(HOTSPOT_RECHECK_INTERVAL)
                    continue
        except Exception:
            # A monitor hiccup should never take the background thread down.
            pass
        time.sleep(POLL_INTERVAL)


def start():
    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        thread = threading.Thread(target=_worker, daemon=True, name="network-monitor")
        thread.start()


def set_auto(enabled):
    global auto_enabled
    auto_enabled = bool(enabled)
