import os
import sqlite3
import threading
import time

import psutil


# Logged on a steady clock rather than jittered — the point of a
# fixed interval is that gaps in the timeline (system asleep,
# service restarted) are easy to spot as gaps, instead of blurring
# into normal sampling noise.
LOG_INTERVAL_SECONDS = 60

# A week of samples at one per minute is ~10k rows — trivial for
# sqlite, and covers the longest range the dashboard offers (1w).
RETENTION_HOURS = 24 * 7

DB_PATH = os.path.join(os.path.dirname(__file__), "data", "battery_history.db")

_started = False
_start_lock = threading.Lock()


def _ensure_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS battery_samples (
                ts INTEGER PRIMARY KEY,
                percent REAL NOT NULL,
                charging INTEGER NOT NULL
            )
            """
        )


def _log_once():
    # psutil.sensors_battery() reads /sys/class/power_supply under the
    # hood on Linux (Arch included) via the kernel's power_supply
    # class, so there's nothing Arch-specific to shell out to here —
    # no acpi/upower calls needed, this works the same everywhere
    # psutil supports a battery at all. Desktops without a battery
    # (or a VM) just get None back, so we skip the write.
    battery = psutil.sensors_battery()
    if not battery:
        return

    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO battery_samples (ts, percent, charging) VALUES (?, ?, ?)",
            (now, float(battery.percent), int(battery.power_plugged)),
        )
        cutoff = now - RETENTION_HOURS * 3600
        conn.execute("DELETE FROM battery_samples WHERE ts < ?", (cutoff,))


def _worker():
    _ensure_db()
    while True:
        try:
            _log_once()
        except Exception:
            # A logging hiccup (locked db, transient psutil error,
            # whatever) should never take the background thread down.
            pass
        time.sleep(LOG_INTERVAL_SECONDS)


def start_logging():
    """
    Idempotent: safe to call from multiple import sites (e.g. under
    a dev-server reloader) without spawning duplicate threads.
    """

    global _started
    with _start_lock:
        if _started:
            return
        _started = True
        thread = threading.Thread(target=_worker, daemon=True, name="battery-logger")
        thread.start()


def get_history(hours=12, max_points=60):
    """
    Returns battery history over the trailing `hours`, downsampled to
    at most `max_points` buckets so the payload stays small no matter
    how dense the raw samples are. Each point is
    {"ts": unix_seconds, "percent": float, "charging": bool}.
    """

    _ensure_db()
    now = int(time.time())
    cutoff = now - hours * 3600

    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT ts, percent, charging FROM battery_samples WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()

    if not rows:
        return []

    if len(rows) <= max_points:
        return [
            {"ts": ts, "percent": round(percent, 1), "charging": bool(charging)}
            for ts, percent, charging in rows
        ]

    span = rows[-1][0] - rows[0][0]
    bucket_span = (span / max_points) or 1
    buckets = {}
    for ts, percent, charging in rows:
        idx = int((ts - rows[0][0]) / bucket_span)
        buckets.setdefault(idx, []).append((ts, percent, charging))

    history = []
    for idx in sorted(buckets):
        bucket = buckets[idx]
        avg_ts = int(sum(b[0] for b in bucket) / len(bucket))
        avg_percent = sum(b[1] for b in bucket) / len(bucket)
        any_charging = any(b[2] for b in bucket)
        history.append({
            "ts": avg_ts,
            "percent": round(avg_percent, 1),
            "charging": any_charging,
        })
    return history


# Module-level side effect, same pattern as the network-rate baseline
# captured at import time in system.py: importing this module (which
# routes.py does, to expose the history endpoint) is what boots the
# background sampler, so nothing extra needs wiring up at app startup.
start_logging()
