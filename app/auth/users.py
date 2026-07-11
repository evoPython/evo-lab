from werkzeug.security import generate_password_hash, check_password_hash

from app.core.db import get_db


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
    db = get_db()
    db.execute(
        "UPDATE users SET last_seen = CURRENT_TIMESTAMP WHERE username = ?",
        (username,),
    )
    db.commit()


def list_online(threshold_seconds=60):
    db = get_db()
    rows = db.execute(
        "SELECT username FROM users "
        "WHERE last_seen >= datetime('now', ?) "
        "ORDER BY username",
        (f"-{threshold_seconds} seconds",),
    ).fetchall()
    return [r["username"] for r in rows]
