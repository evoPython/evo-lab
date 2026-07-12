import sqlite3

from flask import current_app, g


def get_db():
    if "db" not in g:
        # `timeout` controls how long SQLite will wait for a lock held by
        # another connection before giving up (Python's sqlite3 default is
        # only 5s). With several devices polling chats/calls concurrently
        # via the threaded dev server, short waits here were surfacing as
        # "database is locked" -> 500s on the Cross Remote endpoints.
        g.db = sqlite3.connect(current_app.config["DB_PATH"], timeout=30)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")

        # WAL lets readers and a writer proceed concurrently instead of the
        # default rollback-journal mode, which takes an exclusive lock for
        # the whole file on every write. This is the main fix for the
        # locking errors under simultaneous multi-device access.
        g.db.execute("PRAGMA journal_mode = WAL")
        g.db.execute("PRAGMA synchronous = NORMAL")
        # Belt-and-suspenders: also set SQLite's own busy timeout (ms) so
        # any connection opened elsewhere without our Python-level timeout
        # still waits instead of failing immediately.
        g.db.execute("PRAGMA busy_timeout = 30000")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sender TEXT NOT NULL,
    recipient TEXT NOT NULL,
    body TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS letters (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    body TEXT NOT NULL,
    ip TEXT NOT NULL,
    visitor_id TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    read INTEGER NOT NULL DEFAULT 0
);

-- One row per visitor_id cookie. Lets the "letter" feature recognize
-- repeat senders without any login, and keeps a light note of the
-- device they last wrote from (all self-reported by the browser, not
-- fingerprinting).
CREATE TABLE IF NOT EXISTS visitors (
    id TEXT PRIMARY KEY,
    first_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP,
    letters_sent INTEGER NOT NULL DEFAULT 0,
    last_ip TEXT,
    user_agent TEXT,
    platform TEXT,
    language TEXT,
    screen TEXT,
    timezone TEXT
);

CREATE TABLE IF NOT EXISTS calls (
    id TEXT PRIMARY KEY,
    caller TEXT NOT NULL,
    callee TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ringing',
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS call_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    call_id TEXT NOT NULL,
    sender TEXT NOT NULL,
    kind TEXT NOT NULL,
    data TEXT NOT NULL,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);
"""


def init_db(app):
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)

        # Migration: older DBs may have a `letters` table from before the
        # visitor_id column existed. CREATE TABLE IF NOT EXISTS above won't
        # retrofit that, so add it by hand if it's missing.
        cols = {row["name"] for row in db.execute("PRAGMA table_info(letters)")}
        if "visitor_id" not in cols:
            db.execute("ALTER TABLE letters ADD COLUMN visitor_id TEXT")

        db.commit()
    app.teardown_appcontext(close_db)
