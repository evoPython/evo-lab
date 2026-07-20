"""Persistent page cache keyed by user and cache key."""

import json
import sqlite3
from datetime import datetime, timezone

from flask import session

DB_PATH = "data.db"


def _get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _user_id():
    auth_id = session.get("auth_id")
    if auth_id:
        from services.auth_store import get_auth_session

        row = get_auth_session(auth_id)
        if row:
            return row["username"]

    return session.get("username")


def get_page_cache(key):
    user_id = _user_id()
    if not user_id:
        return None

    conn = _get_db()
    try:
        row = conn.execute(
            "SELECT payload FROM page_cache WHERE user_id = ? AND cache_key = ?",
            (user_id, key),
        ).fetchone()
    finally:
        conn.close()

    if not row:
        return None

    try:
        return json.loads(row["payload"])
    except (json.JSONDecodeError, TypeError):
        return None


def set_page_cache(key, payload):
    user_id = _user_id()
    if not user_id:
        return

    now = datetime.now(timezone.utc).isoformat()
    encoded = json.dumps(payload, default=str)

    conn = _get_db()
    try:
        conn.execute(
            """
            INSERT INTO page_cache (user_id, cache_key, payload, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id, cache_key) DO UPDATE SET
                payload = excluded.payload,
                updated_at = excluded.updated_at
            """,
            (user_id, key, encoded, now),
        )
        conn.commit()
    finally:
        conn.close()


def delete_page_cache(key):
    user_id = _user_id()
    if not user_id:
        return

    conn = _get_db()
    try:
        conn.execute(
            "DELETE FROM page_cache WHERE user_id = ? AND cache_key = ?",
            (user_id, key),
        )
        conn.commit()
    finally:
        conn.close()


def delete_page_cache_prefix(prefix):
    user_id = _user_id()
    if not user_id:
        return

    conn = _get_db()
    try:
        conn.execute(
            "DELETE FROM page_cache WHERE user_id = ? AND cache_key LIKE ?",
            (user_id, f"{prefix}%"),
        )
        conn.commit()
    finally:
        conn.close()


def clear_page_cache():
    user_id = _user_id()
    if not user_id:
        return

    conn = _get_db()
    try:
        conn.execute("DELETE FROM page_cache WHERE user_id = ?", (user_id,))
        conn.commit()
    finally:
        conn.close()
