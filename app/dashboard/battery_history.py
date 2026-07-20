import os
import sqlite3
import threading
import time

from app.dashboard.system import get_battery


# Logged on a steady clock rather than jittered — the point of a
# fixed interval is that gaps in the timeline (system asleep,
# service restarted) are easy to spot as gaps, instead of blurring
# into normal sampling noise.
LOG_INTERVAL_SECONDS = 30

# A month of samples at one per 30s is ~86k rows — still trivial for
# sqlite, and covers the longest range the dashboard offers (1month).
RETENTION_HOURS = 24 * 31

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
        # Migration for dbs created before wattage logging existed.
        try:
            conn.execute("ALTER TABLE battery_samples ADD COLUMN watts REAL")
        except sqlite3.OperationalError:
            pass  # column already there


def _log_once():
    # get_battery() reads /sys/class/power_supply under the hood on
    # Linux (Arch included) — no acpi/upower shelling out needed —
    # and also gives us wattage + 2-decimal percent on top of what
    # raw psutil.sensors_battery() exposes. Desktops without a
    # battery (or a VM) just get None back, so we skip the write.
    battery = get_battery()
    if not battery:
        return

    now = int(time.time())
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "INSERT OR REPLACE INTO battery_samples (ts, percent, charging, watts) VALUES (?, ?, ?, ?)",
            (now, float(battery["percent"]), int(battery["charging"]), battery["watts"]),
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
            "SELECT ts, percent, charging, watts FROM battery_samples WHERE ts >= ? ORDER BY ts ASC",
            (cutoff,),
        ).fetchall()

    if not rows:
        return []

    if len(rows) <= max_points:
        return [
            {
                "ts": ts,
                "percent": round(percent, 1),
                "charging": bool(charging),
                "watts": round(watts, 2) if watts is not None else None,
            }
            for ts, percent, charging, watts in rows
        ]

    span = rows[-1][0] - rows[0][0]
    bucket_span = (span / max_points) or 1
    buckets = {}
    for ts, percent, charging, watts in rows:
        idx = int((ts - rows[0][0]) / bucket_span)
        buckets.setdefault(idx, []).append((ts, percent, charging, watts))

    history = []
    for idx in sorted(buckets):
        bucket = buckets[idx]
        avg_ts = int(sum(b[0] for b in bucket) / len(bucket))
        avg_percent = sum(b[1] for b in bucket) / len(bucket)
        any_charging = any(b[2] for b in bucket)
        watt_vals = [b[3] for b in bucket if b[3] is not None]
        avg_watts = (sum(watt_vals) / len(watt_vals)) if watt_vals else None
        history.append({
            "ts": avg_ts,
            "percent": round(avg_percent, 1),
            "charging": any_charging,
            "watts": round(avg_watts, 2) if avg_watts is not None else None,
        })
    return history


# Module-level side effect, same pattern as the network-rate baseline
# captured at import time in system.py: importing this module (which
# routes.py does, to expose the history endpoint) is what boots the
# background sampler, so nothing extra needs wiring up at app startup.
start_logging()
