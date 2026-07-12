import uuid

from flask import Blueprint, render_template, request, jsonify, redirect, url_for

from app.core.db import get_db
from app.core.security import require_personal_device


letters = Blueprint(
    "letters",
    __name__,
    url_prefix="/letters"
)

MAX_NAME_LEN = 80
MAX_BODY_LEN = 4000

# Simple, DB-backed rate limit: no more than RATE_LIMIT_MAX letters
# from the same IP within RATE_LIMIT_WINDOW_HOURS. Persists across
# restarts since it's just a COUNT() query, no extra deps needed.
RATE_LIMIT_MAX = 8
RATE_LIMIT_WINDOW_HOURS = 24

# visitor_id cookie: an anonymous, random token used only to notice
# "this is the same browser as before" for the letter box. It carries
# no personal info by itself.
VISITOR_COOKIE = "visitor_id"
VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 365 * 2  # ~2 years

# Fields the client may self-report about its device. Nothing here is
# fingerprinting-grade — it's the same handful of values any analytics
# snippet would see, kept short and capped.
DEVICE_FIELDS = ("platform", "language", "screen", "timezone")
MAX_DEVICE_FIELD_LEN = 120


def _client_ip():
    return request.remote_addr or "unknown"


def _rate_limited(ip):
    db = get_db()
    row = db.execute(
        "SELECT COUNT(*) AS n FROM letters "
        "WHERE ip = ? AND created_at >= datetime('now', ?)",
        (ip, f"-{RATE_LIMIT_WINDOW_HOURS} hours"),
    ).fetchone()
    return row["n"] >= RATE_LIMIT_MAX


def _get_or_create_visitor_id():
    """
    Reads the visitor_id cookie off the incoming request. Returns
    (visitor_id, is_new) — is_new tells the caller whether a cookie
    needs to be set on the outgoing response.
    """
    vid = request.cookies.get(VISITOR_COOKIE)
    if vid:
        # Reject anything that isn't shaped like a UUID we issued.
        try:
            uuid.UUID(vid)
            return vid, False
        except (ValueError, AttributeError):
            pass
    return str(uuid.uuid4()), True


def _upsert_visitor(visitor_id, ip, device):
    db = get_db()
    device = device or {}
    user_agent = (request.headers.get("User-Agent") or "")[:MAX_DEVICE_FIELD_LEN]
    fields = {
        k: str(device.get(k, ""))[:MAX_DEVICE_FIELD_LEN] or None
        for k in DEVICE_FIELDS
    }

    db.execute(
        """
        INSERT INTO visitors (id, last_ip, user_agent, platform, language, screen, timezone, letters_sent)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(id) DO UPDATE SET
            last_seen = CURRENT_TIMESTAMP,
            last_ip = excluded.last_ip,
            user_agent = excluded.user_agent,
            platform = excluded.platform,
            language = excluded.language,
            screen = excluded.screen,
            timezone = excluded.timezone,
            letters_sent = letters_sent + 1
        """,
        (
            visitor_id,
            ip,
            user_agent,
            fields["platform"],
            fields["language"],
            fields["screen"],
            fields["timezone"],
        ),
    )


def _set_visitor_cookie(resp, visitor_id):
    resp.set_cookie(
        VISITOR_COOKIE,
        visitor_id,
        max_age=VISITOR_COOKIE_MAX_AGE,
        httponly=True,
        samesite="Lax",
    )
    return resp


@letters.route("/send", methods=["POST"])
def send_letter():
    data = request.get_json(silent=True) or request.form

    name = (data.get("name") or "").strip()[:MAX_NAME_LEN]
    body = (data.get("body") or "").strip()
    device = data.get("device") if isinstance(data.get("device"), dict) else {}

    if not body:
        return jsonify(error="write something first."), 400
    if len(body) > MAX_BODY_LEN:
        return jsonify(error="that's a bit long — keep it under 4000 characters."), 400

    ip = _client_ip()
    if _rate_limited(ip):
        return jsonify(error="you've sent a few letters already — give it a rest for now."), 429

    visitor_id, _ = _get_or_create_visitor_id()

    db = get_db()
    db.execute(
        "INSERT INTO letters (name, body, ip, visitor_id) VALUES (?, ?, ?, ?)",
        (name or None, body[:MAX_BODY_LEN], ip, visitor_id),
    )
    _upsert_visitor(visitor_id, ip, device)
    db.commit()

    total = db.execute("SELECT COUNT(*) AS n FROM letters").fetchone()["n"]

    resp = jsonify(ok=True, total=total)
    return _set_visitor_cookie(resp, visitor_id)


@letters.route("/count")
def letter_count():
    db = get_db()
    total = db.execute("SELECT COUNT(*) AS n FROM letters").fetchone()["n"]
    resp = jsonify(total=total)

    # Piggyback the visitor cookie here too, so a first-time visitor who
    # never sends a letter still gets recognized if they come back later,
    # without writing anything to the DB on every page load.
    visitor_id, is_new_visitor = _get_or_create_visitor_id()
    if is_new_visitor:
        _set_visitor_cookie(resp, visitor_id)
    return resp


@letters.route("/inbox")
@require_personal_device
def inbox():
    db = get_db()
    rows = db.execute(
        "SELECT l.id, l.name, l.body, l.ip, l.visitor_id, l.created_at, l.read, "
        "       v.letters_sent AS visitor_letters_sent, v.first_seen AS visitor_first_seen, "
        "       v.user_agent AS visitor_user_agent, v.platform AS visitor_platform, "
        "       v.language AS visitor_language, v.screen AS visitor_screen, "
        "       v.timezone AS visitor_timezone "
        "FROM letters l "
        "LEFT JOIN visitors v ON v.id = l.visitor_id "
        "ORDER BY l.id DESC"
    ).fetchall()

    # Viewing the inbox is what "reads" the letters, for badge purposes.
    db.execute("UPDATE letters SET read = 1 WHERE read = 0")
    db.commit()

    return render_template("inbox.html", letters=rows)


@letters.route("/<int:letter_id>/delete", methods=["POST"])
@require_personal_device
def delete_letter(letter_id):
    db = get_db()
    db.execute("DELETE FROM letters WHERE id = ?", (letter_id,))
    db.commit()
    return redirect(url_for("letters.inbox"))
