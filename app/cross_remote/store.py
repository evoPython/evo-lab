import uuid

from app.core.db import get_db


# --- messages ---

def send_message(sender, recipient, body):
    db = get_db()
    db.execute(
        "INSERT INTO messages (sender, recipient, body) VALUES (?, ?, ?)",
        (sender, recipient, body),
    )
    db.commit()


def get_conversation(user_a, user_b, since_id=0):
    db = get_db()
    rows = db.execute(
        "SELECT id, sender, recipient, body, created_at FROM messages "
        "WHERE id > ? AND "
        "((sender = ? AND recipient = ?) OR (sender = ? AND recipient = ?)) "
        "ORDER BY id ASC",
        (since_id, user_a, user_b, user_b, user_a),
    ).fetchall()
    return [dict(r) for r in rows]


# --- calls ---

def create_call(caller, callee):
    db = get_db()
    call_id = uuid.uuid4().hex
    db.execute(
        "INSERT INTO calls (id, caller, callee, status) VALUES (?, ?, ?, 'ringing')",
        (call_id, caller, callee),
    )
    db.commit()
    return call_id


def get_call(call_id):
    db = get_db()
    row = db.execute("SELECT * FROM calls WHERE id = ?", (call_id,)).fetchone()
    return dict(row) if row else None


def set_call_status(call_id, status):
    db = get_db()
    db.execute("UPDATE calls SET status = ? WHERE id = ?", (status, call_id))
    db.commit()


def incoming_calls(username):
    db = get_db()
    rows = db.execute(
        "SELECT * FROM calls WHERE callee = ? AND status = 'ringing' "
        "AND created_at >= datetime('now', '-30 seconds') "
        "ORDER BY created_at DESC LIMIT 1",
        (username,),
    ).fetchall()
    return [dict(r) for r in rows]


def add_signal(call_id, sender, kind, data):
    db = get_db()
    db.execute(
        "INSERT INTO call_signals (call_id, sender, kind, data) VALUES (?, ?, ?, ?)",
        (call_id, sender, kind, data),
    )
    db.commit()


def get_signals(call_id, exclude_sender, since_id=0):
    db = get_db()
    rows = db.execute(
        "SELECT id, sender, kind, data FROM call_signals "
        "WHERE call_id = ? AND sender != ? AND id > ? ORDER BY id ASC",
        (call_id, exclude_sender, since_id),
    ).fetchall()
    return [dict(r) for r in rows]
