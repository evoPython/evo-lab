import time

from werkzeug.security import generate_password_hash, check_password_hash

from app.core.db import get_db


# Cross Remote's chat/call polling hits `require_login` (and therefore
# touch_last_seen) as often as every 2 seconds per connected device. That
# was previously issuing a DB write on every single poll, which is what
# was starving out the actual chat/call writes and producing "database is
# locked" errors under concurrent multi-device use. "Online" only needs
# ~60s resolution (see list_online's threshold), so we debounce writes to
# once every 15s per user instead of once per request.
_LAST_SEEN_WRITE_INTERVAL = 15
_last_seen_write_times = {}


def get_user(username):
    db = get_db()
    return db.execute(
        "SELECT * FROM users WHERE username = ?", (username,)
    ).fetchone()


def create_user(username, password):
    db = get_db()
    db.execute(
        "INSERT INTO users (username, password_hash) VALUES (?, ?)",
        (username, generate_password_hash(password)),
    )
    db.commit()


def verify_user(username, password):
    user = get_user(username)
    if user and check_password_hash(user["password_hash"], password):
        return user
    return None


def touch_last_seen(username):
    now = time.monotonic()
    last_write = _last_seen_write_times.get(username, 0)
    if now - last_write < _LAST_SEEN_WRITE_INTERVAL:
        return

    db = get_db()
    db.execute(
        "UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE username = ?",
        (username,),
    )
    db.commit()
    _last_seen_write_times[username] = now


def list_online(threshold_seconds=60):
    db = get_db()
    rows = db.execute(
        "SELECT username FROM users "
        "WHERE last_seen >= datetime('now', ?) "
        "ORDER BY username",
        (f"-{threshold_seconds} seconds",),
    ).fetchall()
    return [r["username"] for r in rows]
