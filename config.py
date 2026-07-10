import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:

    SECRET_KEY = os.getenv(
        "SECRET_KEY"
    )

    # Root login password (single shared secret, unlocks remote-access
    # features: controls, tools, niri, media, launcher).
    ROOT_PASSWORD = os.getenv(
        "ROOT_PASSWORD"
    )

    # SQLite db for personal accounts, chat, and call signaling.
    DB_PATH = os.getenv(
        "EVO_DB_PATH",
        os.path.join(BASE_DIR, "data", "evo.db")
    )

    # Where uploaded files from the file transfer tool are stored.
    UPLOAD_DIR = os.getenv(
        "EVO_UPLOAD_DIR",
        os.path.join(BASE_DIR, "data", "uploads")
    )

    # Upload size limit in MB, converted to bytes for Flask.
    MAX_CONTENT_LENGTH = int(
        os.getenv("EVO_MAX_UPLOAD_MB", "200")
    ) * 1024 * 1024
