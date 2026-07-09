import os
from dotenv import load_dotenv

load_dotenv()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:

    SECRET_KEY = os.getenv(
        "SECRET_KEY"
    )

    DEVICE_TOKEN = os.getenv(
        "DEVICE_TOKEN"
    )

    # Where uploaded files from the file transfer tool are stored.
    # Kept out of the source tree by default (data/uploads) and
    # overridable via .env for a custom path (e.g. an external drive).
    UPLOAD_DIR = os.getenv(
        "EVO_UPLOAD_DIR",
        os.path.join(BASE_DIR, "data", "uploads")
    )

    # Upload size limit in MB, converted to bytes for Flask.
    MAX_CONTENT_LENGTH = int(
        os.getenv("EVO_MAX_UPLOAD_MB", "200")
    ) * 1024 * 1024
