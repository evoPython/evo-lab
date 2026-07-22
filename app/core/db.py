import json
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

-- Single-row table holding the "my status" text shown on the public
-- home page and editable from Site Management. Always id = 1.
-- `mode` is a Discord-style presence indicator: online / idle / offline.
CREATE TABLE IF NOT EXISTS site_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    status TEXT NOT NULL DEFAULT 'around',
    mode TEXT NOT NULL DEFAULT 'online',
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
INSERT OR IGNORE INTO site_status (id, status) VALUES (1, 'around');

-- Tracks anyone currently browsing the site — logged-in users and
-- anonymous visitors alike — keyed by a stable identity per browser
-- (username if logged in, else the visitor_id cookie). Updated on
-- every page view so Site Management can show who's online and what
-- page they're on right now.
CREATE TABLE IF NOT EXISTS presence (
    key TEXT PRIMARY KEY,
    kind TEXT NOT NULL,
    label TEXT NOT NULL,
    visitor_id TEXT,
    ip TEXT,
    user_agent TEXT,
    path TEXT,
    last_seen TEXT DEFAULT CURRENT_TIMESTAMP
);

-- Single-row table holding the class schedule shown on the public
-- home page (#about) and editable from Site Management. Always id = 1.
-- `schedule_json` is a list of periods: [{start, end, classes: [mon..fri]}].
-- `holiday` overrides the schedule display with "HOLIDAY" when set.
CREATE TABLE IF NOT EXISTS class_schedule (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    schedule_json TEXT NOT NULL DEFAULT '[]',
    holiday INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
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

        status_cols = {row["name"] for row in db.execute("PRAGMA table_info(site_status)")}
        if "mode" not in status_cols:
            db.execute("ALTER TABLE site_status ADD COLUMN mode TEXT NOT NULL DEFAULT 'online'")
            db.execute("UPDATE site_status SET mode = 'online' WHERE mode IS NULL")

        # Seed the class schedule with its default timetable the first time
        # the table is created. Deferred import to avoid a circular import
        # (app.core.schedule imports get_db from this module).
        from app.core.schedule import DEFAULT_SCHEDULE
        db.execute(
            "INSERT OR IGNORE INTO class_schedule (id, schedule_json) VALUES (1, ?)",
            (json.dumps(DEFAULT_SCHEDULE),),
        )

        db.commit()
    app.teardown_appcontext(close_db)
