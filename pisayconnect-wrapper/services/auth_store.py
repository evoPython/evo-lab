"""Server-side auth sessions so large API tokens are not stored in cookies."""

import secrets
import sqlite3
from datetime import datetime, timezone

DB_PATH = "data.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_auth_table(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS auth_sessions (
            id TEXT PRIMARY KEY,
            token TEXT NOT NULL,
            username TEXT NOT NULL,
            student_id INTEGER,
            account_type TEXT,
            debug_mode INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
        """
    )


def create_auth_session(token, username, *, student_id=None, account_type="student"):
    session_id = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc).isoformat()

    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT INTO auth_sessions
                (id, token, username, student_id, account_type, debug_mode, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, 0, ?, ?)
            """,
            (session_id, token, username, student_id, account_type, now, now),
        )
        conn.commit()
    finally:
        conn.close()

    return session_id


def get_auth_session(session_id):
    if not session_id:
        return None

    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT * FROM auth_sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
    finally:
        conn.close()

    return dict(row) if row else None


def update_auth_session(session_id, **fields):
    if not session_id or not fields:
        return

    allowed = {"student_id", "debug_mode", "token", "username", "account_type"}
    updates = {key: value for key, value in fields.items() if key in allowed}
    if not updates:
        return

    updates["updated_at"] = datetime.now(timezone.utc).isoformat()
    columns = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [session_id]

    conn = _get_db()
    try:
        conn.execute(
            f"UPDATE auth_sessions SET {columns} WHERE id = ?",
            values,
        )
        conn.commit()
    finally:
        conn.close()


def delete_auth_session(session_id):
    if not session_id:
        return

    conn = _get_db()
    try:
        conn.execute("DELETE FROM auth_sessions WHERE id = ?", (session_id,))
        conn.commit()
    finally:
        conn.close()
