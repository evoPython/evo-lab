from app.core.db import get_db

DEFAULT_STATUS = "around"
DEFAULT_MODE = "online"
VALID_MODES = ("online", "idle", "offline")


def get_status():
    """Returns (status_text, mode, updated_at)."""
    db = get_db()
    row = db.execute(
        "SELECT status, mode, updated_at FROM site_status WHERE id = 1"
    ).fetchone()
    if row:
        return row["status"], row["mode"] or DEFAULT_MODE, row["updated_at"]
    return DEFAULT_STATUS, DEFAULT_MODE, None


def set_status(text, mode=None):
    if mode not in VALID_MODES:
        mode = DEFAULT_MODE
    db = get_db()
    db.execute(
        "UPDATE site_status SET status = ?, mode = ?, updated_at = CURRENT_TIMESTAMP WHERE id = 1",
        (text, mode),
    )
    db.commit()
