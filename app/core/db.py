import sqlite3

from flask import current_app, g


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(current_app.config["DB_PATH"])
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
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
        db.commit()
    app.teardown_appcontext(close_db)
