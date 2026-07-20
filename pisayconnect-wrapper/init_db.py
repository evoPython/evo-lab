import sqlite3

def init_db():
    conn = sqlite3.connect("data.db")
    c = conn.cursor()

    c.execute("""
    CREATE TABLE IF NOT EXISTS bookmarks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        post_id INTEGER NOT NULL,
        UNIQUE(user_id, post_id)
    )
    """)

    c.execute("""
    CREATE TABLE IF NOT EXISTS parent_accounts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_username TEXT NOT NULL,
        parent_username TEXT NOT NULL,
        parent_token TEXT NOT NULL,
        linked_at TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(student_username, parent_username)
    )
    """)

    conn.commit()
    conn.close()
