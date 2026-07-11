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


@letters.route("/send", methods=["POST"])
def send_letter():
    data = request.get_json(silent=True) or request.form

    name = (data.get("name") or "").strip()[:MAX_NAME_LEN]
    body = (data.get("body") or "").strip()

    if not body:
        return jsonify(error="write something first."), 400
    if len(body) > MAX_BODY_LEN:
        return jsonify(error="that's a bit long — keep it under 4000 characters."), 400

    ip = _client_ip()
    if _rate_limited(ip):
        return jsonify(error="you've sent a few letters already — give it a rest for now."), 429

    db = get_db()
    db.execute(
        "INSERT INTO letters (name, body, ip) VALUES (?, ?, ?)",
        (name or None, body[:MAX_BODY_LEN], ip),
    )
    db.commit()

    return jsonify(ok=True)


@letters.route("/inbox")
@require_personal_device
def inbox():
    db = get_db()
    rows = db.execute(
        "SELECT id, name, body, ip, created_at, read FROM letters "
        "ORDER BY id DESC"
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
