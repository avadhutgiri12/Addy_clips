from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Literal
from urllib.parse import urlparse

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field


ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = Path(os.environ.get("ADDY_DATA_DIR", ROOT / "data"))
UPLOAD_DIR = Path(os.environ.get("ADDY_UPLOAD_DIR", ROOT / "uploads"))
OUTPUT_DIR = Path(os.environ.get("ADDY_OUTPUT_DIR", ROOT / "output"))
SETTINGS_PATH = DATA_DIR / "settings.json"
JOBS_PATH = DATA_DIR / "jobs.json"
MAX_UPLOAD_BYTES = 8 * 1024 * 1024 * 1024  # 8 GiB
_lock = Lock()

for folder in (DATA_DIR, UPLOAD_DIR, OUTPUT_DIR):
    folder.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Addy Clips API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "DELETE"],
    allow_headers=["Content-Type"],
)


def read_json(path: Path, fallback):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return fallback


def write_json(path: Path, value) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


def public_job(job: dict) -> dict:
    """Never return private local filesystem paths to the browser."""
    result = dict(job)
    result.pop("file_path", None)
    return result


class SettingsUpdate(BaseModel):
    gemini_api_key: str = Field(max_length=512)


@app.get("/api/health")
def health():
    return {"status": "ok", "app": "Addy Clips", "processing_ready": False}


@app.get("/api/settings")
def get_settings():
    settings = read_json(SETTINGS_PATH, {})
    return {"gemini_configured": bool(settings.get("gemini_api_key"))}


@app.put("/api/settings")
def update_settings(body: SettingsUpdate):
    key = body.gemini_api_key.strip()
    if key and not key.startswith("AIza"):
        raise HTTPException(status_code=422, detail="That does not look like a Gemini API key.")
    write_json(SETTINGS_PATH, {"gemini_api_key": key})
    return {"gemini_configured": bool(key)}


@app.get("/api/jobs")
def get_jobs():
    jobs = read_json(JOBS_PATH, [])
    return {"jobs": [public_job(job) for job in sorted(jobs, key=lambda item: item["created_at"], reverse=True)]}


@app.post("/api/jobs", status_code=202)
async def create_job(
    source: str = Form(..., max_length=2048),
    source_type: Literal["youtube", "live", "upload"] = Form(...),
    clip_count: int = Form(5, ge=1, le=15),
    duration: int = Form(30, ge=15, le=60),
    aspect_ratio: Literal["9:16", "16:9"] = Form("9:16"),
    quality: str = Form("Source resolution", max_length=40),
    prompt: str = Form("", max_length=1000),
    file: UploadFile | None = File(None),
):
    settings = read_json(SETTINGS_PATH, {})
    if not settings.get("gemini_api_key"):
        raise HTTPException(status_code=400, detail="Add your Gemini API key in Settings before creating a clip job.")
    if source_type == "upload" and file is None:
        raise HTTPException(status_code=422, detail="Choose a video file to upload.")
    if source_type != "upload" and file is not None:
        raise HTTPException(status_code=422, detail="Choose either a YouTube link or a video upload.")

    file_path = None
    display_source = source.strip()
    if file is not None:
        filename = Path(file.filename or "video.mp4").name
        suffix = Path(filename).suffix.lower()
        if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".m4v"}:
            raise HTTPException(status_code=415, detail="Supported video formats: MP4, MOV, MKV, WEBM, and M4V.")
        job_id = uuid.uuid4().hex[:12]
        target = UPLOAD_DIR / f"{job_id}{suffix}"
        size = 0
        try:
            with target.open("wb") as stream:
                while chunk := await file.read(1024 * 1024):
                    size += len(chunk)
                    if size > MAX_UPLOAD_BYTES:
                        raise HTTPException(status_code=413, detail="Video uploads are limited to 8 GiB.")
                    stream.write(chunk)
        except Exception:
            target.unlink(missing_ok=True)
            raise
        finally:
            await file.close()
        file_path = str(target)
        display_source = filename
    else:
        job_id = uuid.uuid4().hex[:12]
        parsed = urlparse(display_source)
        host = (parsed.hostname or "").lower()
        youtube_host = host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com") or host == "youtube-nocookie.com" or host.endswith(".youtube-nocookie.com")
        if parsed.scheme not in {"http", "https"} or not youtube_host:
            raise HTTPException(status_code=422, detail="Enter a valid YouTube video or live stream URL.")

    job = {
        "id": job_id,
        "source": display_source,
        "source_type": source_type,
        "status": "queued",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "title": None,
        "clips": 0,
        "progress": 0,
        "message": "Queued locally. Video processing is not connected yet.",
        "settings": {"clip_count": clip_count, "duration": duration, "aspect_ratio": aspect_ratio, "quality": quality, "prompt": prompt},
        "file_path": file_path,
    }
    with _lock:
        jobs = read_json(JOBS_PATH, [])
        jobs.append(job)
        write_json(JOBS_PATH, jobs)
    return {"job": public_job(job)}


@app.delete("/api/jobs/{job_id}")
def delete_job(job_id: str):
    with _lock:
        jobs = read_json(JOBS_PATH, [])
        match = next((job for job in jobs if job["id"] == job_id), None)
        if match is None:
            raise HTTPException(status_code=404, detail="Job not found.")
        if match.get("file_path"):
            Path(match["file_path"]).unlink(missing_ok=True)
        jobs = [job for job in jobs if job["id"] != job_id]
        write_json(JOBS_PATH, jobs)
    return {"deleted": True}
