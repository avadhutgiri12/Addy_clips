import os
from pathlib import Path

DATA_DIR = Path(os.getenv("DATA_DIR", "./data")).resolve()
MAX_UPLOAD_SIZE_MB = int(os.getenv("MAX_UPLOAD_SIZE_MB", "2048"))
MAX_VIDEO_DURATION_MINUTES = int(os.getenv("MAX_VIDEO_DURATION_MINUTES", "180"))
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY", "")
API_INTERNAL_URL = os.getenv("API_INTERNAL_URL", "http://127.0.0.1:8000")
YOUTUBE_LIVE_DOWNLOAD_DURATION_MINUTES = int(os.getenv("YOUTUBE_LIVE_DOWNLOAD_DURATION_MINUTES", "20"))
DOWNLOAD_DIR = DATA_DIR / "download"

for folder in ("clips", "projects", "temp", "database", "logs", "download"):
    (DATA_DIR / folder).mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "database" / "addy-clips.sqlite3"

