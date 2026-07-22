import time
import uuid

from flask import request, session, g

from app.core.db import get_db

# Generic "which browser is this" cookie, separate from any login.
# Reused as-is by the letters feature too (same shape), but this is
# now the site-wide source of truth, set on any page view.
PRESENCE_COOKIE = "visitor_id"
PRESENCE_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # ~2 years

# "Online" = a page view within this many seconds.
ONLINE_THRESHOLD_SECONDS = 60

# Only debounce the DB write per identity, not the whole request, so
# path/IP still feel live without hammering SQLite on every request
# (same reasoning as touch_last_seen in app/auth/users.py).
_WRITE_INTERVAL = 5
_last_write_times = {}


def _client_ip():
    return request.remote_addr or "unknown"


def _get_or_create_visitor_id():
    vid = request.cookies.get(PRESENCE_COOKIE)
    if vid:
        try:
            uuid.UUID(vid)
            return vid, False
        except (ValueError, AttributeError):
            pass
    return str(uuid.uuid4()), True


def track_request():
    """before_request hook: note that this identity is on `request.path` right now."""
    if request.path.startswith("/static"):
        return

    vid, is_new = _get_or_create_visitor_id()
    g._presence_visitor_id = vid
    g._presence_visitor_new = is_new

    username = session.get("user_id")
    key = f"user:{username}" if username else f"visitor:{vid}"

    now = time.monotonic()
    if now - _last_write_times.get(key, 0) < _WRITE_INTERVAL:
        return
    _last_write_times[key] = now

    # Distinguish real page navigations from background JSON/polling
    # requests (dashboard stats, letter-count checks, etc.) so "where
    # they are" reflects the last page they actually opened, not
    # whatever endpoint their browser happened to poll most recently.
    is_page_view = request.method == "GET" and request.accept_mimetypes.accept_html

    db = get_db()
    db.execute(
        """
        INSERT INTO presence (key, kind, label, visitor_id, ip, user_agent, path, last_seen)
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET
            label = excluded.label,
            visitor_id = excluded.visitor_id,
            ip = excluded.ip,
            user_agent = excluded.user_agent,
            path = CASE WHEN ? = 1 THEN excluded.path ELSE presence.path END,
            last_seen = CURRENT_TIMESTAMP
        """,
        (
            key,
            "user" if username else "visitor",
            username or vid,
            vid,
            _client_ip(),
            (request.headers.get("User-Agent") or "")[:200],
            request.path,
            1 if is_page_view else 0,
        ),
    )
    db.commit()


def attach_cookie(response):
    """after_request hook: hand out the visitor_id cookie to first-timers."""
    if getattr(g, "_presence_visitor_new", False):
        response.set_cookie(
            PRESENCE_COOKIE,
            g._presence_visitor_id,
            max_age=PRESENCE_COOKIE_MAX_AGE,
            httponly=True,
            samesite="Lax",
        )
    return response


def list_online(threshold_seconds=ONLINE_THRESHOLD_SECONDS):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM presence WHERE last_seen >= datetime('now', ?) "
        "ORDER BY last_seen DESC",
        (f"-{threshold_seconds} seconds",),
    ).fetchall()
    return [dict(r) for r in rows]
