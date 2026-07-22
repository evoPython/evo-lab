from flask import Blueprint, render_template, request, redirect, url_for, jsonify

from app.core.db import get_db
from app.core.security import require_personal_device
from app.core.status import get_status, set_status, VALID_MODES
from app.core.presence import list_online
from app.core.schedule import get_schedule, set_schedule, set_holiday, DAYS

MAX_STATUS_LEN = 120

management = Blueprint(
    "management",
    __name__,
    url_prefix="/management"
)


@management.route("/")
@require_personal_device
def index():
    db = get_db()

    visitors = db.execute(
        "SELECT * FROM visitors ORDER BY last_seen DESC"
    ).fetchall()

    letters = db.execute(
        "SELECT l.id, l.name, l.body, l.ip, l.visitor_id, l.created_at, l.read, "
        "       v.letters_sent AS visitor_letters_sent, v.first_seen AS visitor_first_seen, "
        "       v.user_agent AS visitor_user_agent, v.platform AS visitor_platform, "
        "       v.language AS visitor_language, v.screen AS visitor_screen, "
        "       v.timezone AS visitor_timezone "
        "FROM letters l "
        "LEFT JOIN visitors v ON v.id = l.visitor_id "
        "ORDER BY l.id DESC"
    ).fetchall()

    # Viewing the page is what "reads" the letters, for badge purposes.
    db.execute("UPDATE letters SET read = 1 WHERE read = 0")
    db.commit()

    status_text, status_mode, status_updated = get_status()
    schedule_periods, schedule_holiday, schedule_updated = get_schedule()

    return render_template(
        "management.html",
        visitors=visitors,
        letters=letters,
        online=list_online(),
        status_text=status_text,
        status_mode=status_mode,
        status_updated=status_updated,
        status_modes=VALID_MODES,
        schedule_periods=schedule_periods,
        schedule_holiday=schedule_holiday,
        schedule_updated=schedule_updated,
        schedule_days=DAYS,
    )


@management.route("/api/online")
@require_personal_device
def api_online():
    return jsonify(online=list_online())


@management.route("/status", methods=["POST"])
@require_personal_device
def update_status():
    text = (request.form.get("status") or "").strip()[:MAX_STATUS_LEN]
    mode = request.form.get("mode")
    if text:
        set_status(text, mode)
    return redirect(url_for("management.index"))


@management.route("/schedule", methods=["POST"])
@require_personal_device
def update_schedule():
    periods = []
    i = 0
    while f"start_{i}" in request.form:
        periods.append({
            "start": (request.form.get(f"start_{i}") or "").strip(),
            "end": (request.form.get(f"end_{i}") or "").strip(),
            "classes": [
                (request.form.get(f"day_{i}_{d}") or "").strip()
                for d in range(len(DAYS))
            ],
        })
        i += 1
    if periods:
        set_schedule(periods)
    return redirect(url_for("management.index") + "#schedule")


@management.route("/schedule/holiday", methods=["POST"])
@require_personal_device
def update_holiday():
    set_holiday(request.form.get("holiday") == "on")
    return redirect(url_for("management.index") + "#schedule")


@management.route("/letters/<int:letter_id>/delete", methods=["POST"])
@require_personal_device
def delete_letter(letter_id):
    db = get_db()
    db.execute("DELETE FROM letters WHERE id = ?", (letter_id,))
    db.commit()
    return redirect(url_for("management.index"))
