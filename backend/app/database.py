import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from .config import DB_PATH

def now():
    return datetime.now(timezone.utc).isoformat()

@contextmanager
def db():
    con = sqlite3.connect(DB_PATH, timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()

def migrate():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS projects (
          id TEXT PRIMARY KEY, title TEXT NOT NULL, source_title TEXT,
          source_url TEXT, source_path TEXT, duration REAL NOT NULL DEFAULT 0,
          created_at TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS jobs (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          status TEXT NOT NULL, stage TEXT NOT NULL, progress INTEGER NOT NULL DEFAULT 0,
          config_json TEXT NOT NULL, error TEXT, cancel_requested INTEGER NOT NULL DEFAULT 0,
          attempts INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, created_at TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS jobs_status_created ON jobs(status, created_at);
        CREATE TABLE IF NOT EXISTS clips (
          id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
          title TEXT NOT NULL, description TEXT NOT NULL DEFAULT '', hashtags_json TEXT NOT NULL DEFAULT '[]',
          start REAL NOT NULL, end REAL NOT NULL, score INTEGER NOT NULL DEFAULT 0,
          category TEXT NOT NULL DEFAULT 'Action and combat', caption_json TEXT NOT NULL DEFAULT '[]',
          vertical_path TEXT, landscape_path TEXT, thumbnail_path TEXT, status TEXT NOT NULL,
          created_at TEXT NOT NULL, updated_at TEXT NOT NULL
        );
        """)

def row_dict(row):
    return dict(row) if row else None

def clip_dict(row):
    d = dict(row)
    d["hashtags"] = json.loads(d.pop("hashtags_json"))
    d["captions"] = json.loads(d.pop("caption_json"))
    return d

