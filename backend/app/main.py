import asyncio, json, os, re, shutil, uuid
from contextlib import asynccontextmanager
import mimetypes
from pathlib import Path
from fastapi import FastAPI, UploadFile, File, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from .config import DATA_DIR, MAX_UPLOAD_SIZE_MB, MAX_VIDEO_DURATION_MINUTES, YOUTUBE_API_KEY
from .database import db, migrate, now, clip_dict
from .schemas import AnalysisRequest, ClipPatch, SourceRequest
from .services.video import probe
from .services.youtube import metadata
from .services.sources import twitch_source, youtube_live_source
from .services.ai import generate_titles, DEFAULT_MODELS

@asynccontextmanager
async def lifespan(_app):
    migrate()
    yield

app = FastAPI(title="Addy Clips API", version="0.1.0", lifespan=lifespan)
origins = os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")
app.add_middleware(CORSMiddleware, allow_origins=[o.strip() for o in origins], allow_methods=["*"], allow_headers=["*"])
job_keys: dict[str, str] = {}

@app.get("/api/health")
def health(): return {"ok": True, "app": "Addy Clips"}

@app.get("/api/settings/models")
def models(): return {"models": DEFAULT_MODELS, "default": DEFAULT_MODELS[0], "youtube_metadata_enabled": bool(YOUTUBE_API_KEY)}

@app.post("/api/settings/test-key")
async def test_key(payload: dict):
    key = str(payload.get("key", ""))
    if len(key) < 20: raise HTTPException(400, "Enter a Gemini API key.")
    try:
        async with __import__('httpx').AsyncClient(timeout=15) as client:
            r = await client.get("https://generativelanguage.googleapis.com/v1beta/models", headers={"x-goog-api-key": key})
        if r.is_error: raise HTTPException(r.status_code, "Gemini rejected this key. Check it in Google AI Studio.")
        return {"ok": True, "message": "Gemini API key accepted."}
    except HTTPException: raise
    except Exception: raise HTTPException(502, "Could not reach Gemini. Check the API container's network connection.")

@app.post("/api/source/validate")
async def validate_source(req: SourceRequest):
    twitch = twitch_source(req.url)
    if twitch:
        return {"valid": True, "processable": True, "media_access": False, **twitch,
                "metadata_available": False, "access_message": "Twitch source recognized. The worker will verify that it is accessible when analysis starts."}

    yt_live = youtube_live_source(req.url)
    if yt_live:
        # For YouTube live, we can download the stream so media_access is true
        return {"valid": True, "processable": True, "media_access": True, **yt_live,
                "metadata_available": True, "title": "YouTube Live Stream", "channel": "YouTube",
                "duration": "1200", "live": True,
                "access_message": "YouTube live stream detected. The last 20 minutes will be downloaded for clipping."}

    result = await metadata(req.url)
    if result is None: raise HTTPException(400, "Enter a valid YouTube video, Shorts, or live URL.")
    return result

@app.post("/api/source/preview")
async def preview_source(req: SourceRequest): return await validate_source(req)

@app.post("/api/source/local-upload")
async def local_upload(file: UploadFile = File(...)):
    allowed = {".mp4", ".mov", ".mkv", ".webm", ".avi"}
    suffix = Path(file.filename or "video.mp4").suffix.lower()
    if suffix not in allowed: raise HTTPException(400, "Upload an MP4, MOV, MKV, WebM, or AVI file.")
    project_id = str(uuid.uuid4())
    dest_dir = DATA_DIR / "projects" / project_id
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / f"source{suffix}"
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_UPLOAD_SIZE_MB * 1024 * 1024: raise HTTPException(413, f"File exceeds {MAX_UPLOAD_SIZE_MB} MB upload limit.")
                out.write(chunk)
        info = await asyncio.to_thread(probe, dest)
        if info["duration"] <= 0 or info["duration"] > MAX_VIDEO_DURATION_MINUTES * 60:
            raise HTTPException(400, f"Video duration must be between 1 second and {MAX_VIDEO_DURATION_MINUTES} minutes.")
        title = Path(file.filename or "Local video").stem
        with db() as c:
            c.execute("INSERT INTO projects(id,title,source_title,source_url,source_path,duration,created_at,source_type) VALUES(?,?,?,?,?,?,?,?)", (project_id, title, title, None, str(dest), info["duration"], now(), "local"))
        return {"project_id": project_id, "title": title, "filename": file.filename, **info, "source_type": "local", "media_access": True}
    except HTTPException:
        dest.unlink(missing_ok=True); raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        raise HTTPException(400, str(e))

@app.post("/api/analysis/start", status_code=202)
def start_analysis(req: AnalysisRequest):
    twitch = twitch_source(req.source_url) if req.source_url else None
    yt_live = youtube_live_source(req.source_url) if req.source_url else None

    if req.generate_titles and not req.gemini_key:
        raise HTTPException(400, "A Gemini API key is needed only when optional AI titles are enabled.")
    if req.mode == "live" and (not twitch or twitch["source_type"] != "twitch_live"):
        raise HTTPException(400, "Live clipping currently supports a Twitch channel URL.")
    if req.mode == "live" and req.project_id:
        raise HTTPException(400, "Live clipping uses a Twitch channel URL, not an uploaded project.")

    # For VOD mode: allow local project, Twitch VOD, or YouTube live
    if req.mode == "vod" and req.project_id is None:
        valid_source = (twitch and twitch["source_type"] == "twitch_vod") or yt_live
        if not valid_source:
            raise HTTPException(400, "Choose a local video, a Twitch VOD URL, or a YouTube live stream URL.")

    project_id = req.project_id or str(uuid.uuid4())
    with db() as c:
        project = c.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone()
        if req.project_id and not project: raise HTTPException(404, "Project not found.")
        if not project:
            if yt_live:
                title = f"YouTube Live {yt_live['video_id']}"
                source_type = "youtube_live"
            else:
                title = (twitch or {}).get("channel") or f"Twitch VOD {(twitch or {}).get('video_id')}"
                source_type = twitch["source_type"]
            c.execute("INSERT INTO projects(id,title,source_title,source_url,source_path,duration,created_at,source_type) VALUES(?,?,?,?,?,?,?,?)",
                      (project_id, title, title, req.source_url, None, 0, now(), source_type))
        active = c.execute("SELECT id FROM jobs WHERE project_id=? AND status IN ('queued','running','waiting_for_key')", (project_id,)).fetchone()
        if active: raise HTTPException(409, "An analysis for this project is already active.")
        job_id = str(uuid.uuid4())
        config = req.model_dump(exclude={"gemini_key"}) | {"project_id": project_id}
        c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)", (job_id, project_id, "queued", "Queued", 0, json.dumps(config), None, 0, 0, now(), now()))
    if req.generate_titles and req.gemini_key: job_keys[job_id] = req.gemini_key
    return {"job_id": job_id, "project_id": project_id, "status": "queued", "message": "Analysis queued."}

@app.get("/api/analysis")
def list_jobs():
    with db() as c: rows = c.execute("SELECT * FROM jobs ORDER BY created_at DESC LIMIT 30").fetchall()
    return [{**dict(r), "config": json.loads(r["config_json"])} for r in rows]

@app.get("/api/analysis/{job_id}")
def get_job(job_id: str):
    with db() as c: row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    if not row: raise HTTPException(404, "Job not found.")
    return {**dict(row), "config": json.loads(row["config_json"])}

@app.post("/api/analysis/{job_id}/cancel")
def cancel_job(job_id: str):
    with db() as c:
        cur = c.execute("UPDATE jobs SET cancel_requested=1, updated_at=? WHERE id=? AND status IN ('queued','running')", (now(), job_id))
        if not cur.rowcount: raise HTTPException(409, "This job is no longer cancellable.")
    job_keys.pop(job_id, None)
    return {"ok": True}

@app.post("/api/analysis/{job_id}/retry")
def retry_job(job_id: str, payload: dict):
    key = str(payload.get("gemini_key", ""))
    with db() as c:
        row = c.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
        if not row: raise HTTPException(404, "Job not found.")
        if row["status"] not in {"waiting_for_key", "failed", "canceled"}: raise HTTPException(409, "This job cannot be retried in its current state.")
        config=json.loads(row["config_json"])
        if config.get("generate_titles") and len(key)<20: raise HTTPException(400, "Enter a Gemini API key to retry optional title generation.")
        c.execute("UPDATE jobs SET status='queued',stage='Queued for retry',progress=0,error=NULL,cancel_requested=0,updated_at=? WHERE id=?", (now(), job_id))
    if config.get("generate_titles"): job_keys[job_id] = key
    return {"job_id": job_id, "status": "queued", "message": "Analysis queued for retry."}

@app.post("/api/internal/jobs/{job_id}/analyze")
async def internal_analyze(job_id: str, payload: dict, request: Request):
    if request.client.host not in {"127.0.0.1", "::1"} and not request.client.host.startswith("172."):
        raise HTTPException(403, "Internal worker endpoint.")
    key = job_keys.get(job_id)
    if not key: raise HTTPException(428, "Gemini key is not available in API memory. Re-submit it to resume analysis.")
    result = await generate_titles(key, payload.get("model", DEFAULT_MODELS[0]), payload["candidates"])
    return {"items": result}

@app.post("/api/internal/jobs/{job_id}/release")
def release_job_key(job_id: str, request: Request):
    if request.client.host not in {"127.0.0.1", "::1"} and not request.client.host.startswith("172."):
        raise HTTPException(403, "Internal worker endpoint.")
    job_keys.pop(job_id, None)
    return {"ok": True}

@app.get("/api/projects/{project_id}/source")
def source_stream(project_id: str, request: Request):
    with db() as c: row = c.execute("SELECT source_path FROM projects WHERE id=?", (project_id,)).fetchone()
    if not row: raise HTTPException(404, "Project not found.")
    path = Path(row["source_path"]).resolve()
    if not path.is_relative_to((DATA_DIR / "projects").resolve()) or not path.is_file():
        raise HTTPException(404, "Source video not found.")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header:
        return FileResponse(path, media_type=media_type, headers={"Accept-Ranges":"bytes"})
    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match: raise HTTPException(416, "Invalid range.")
    start, end = int(match.group(1) or 0), int(match.group(2) or size - 1)
    if start >= size or end < start: raise HTTPException(416, "Range not satisfiable.")
    end = min(end, size - 1)
    def iterator():
        with path.open("rb") as f:
            f.seek(start); remaining = end - start + 1
            while remaining:
                chunk = f.read(min(1024 * 1024, remaining))
                if not chunk: break
                remaining -= len(chunk); yield chunk
    return StreamingResponse(iterator(), status_code=206, media_type=media_type, headers={"Content-Range":f"bytes {start}-{end}/{size}","Accept-Ranges":"bytes","Content-Length":str(end-start+1)})

def safe_path(raw: str | None) -> Path:
    if not raw: raise HTTPException(404, "This format is not available.")
    p = Path(raw).resolve()
    if not p.is_relative_to((DATA_DIR / "clips").resolve()) or not p.is_file(): raise HTTPException(404, "Clip file not found.")
    return p

@app.get("/api/clips")
def list_clips(search: str = "", category: str = "", offset: int = 0, limit: int = Query(24, ge=1, le=100)):
    with db() as c:
        rows = c.execute("SELECT clips.*, projects.title AS project_title, projects.source_title FROM clips JOIN projects ON projects.id=clips.project_id WHERE clips.status='complete' AND (?='' OR clips.title LIKE ? OR projects.title LIKE ?) AND (?='' OR clips.category=?) ORDER BY clips.created_at DESC LIMIT ? OFFSET ?", (search, f"%{search}%", f"%{search}%", category, category, limit, offset)).fetchall()
    return {"items": [clip_dict(r) for r in rows], "offset": offset, "limit": limit}

@app.get("/api/clips/{clip_id}")
def get_clip(clip_id: str):
    with db() as c: row = c.execute("SELECT * FROM clips WHERE id=? AND status='complete'", (clip_id,)).fetchone()
    if not row: raise HTTPException(404, "Clip not found.")
    return clip_dict(row)

@app.patch("/api/clips/{clip_id}")
def patch_clip(clip_id: str, patch: ClipPatch):
    updates = patch.model_dump(exclude_unset=True)
    if not updates: return get_clip(clip_id)
    fields, values = [], []
    for key, value in updates.items():
        dbkey = {"hashtags": "hashtags_json", "captions": "caption_json"}.get(key, key)
        fields.append(f"{dbkey}=?"); values.append(json.dumps(value) if key in {"hashtags", "captions"} else value)
    fields.append("updated_at=?"); values.extend([now(), clip_id])
    with db() as c: cur = c.execute(f"UPDATE clips SET {','.join(fields)} WHERE id=?", values)
    if not cur.rowcount: raise HTTPException(404, "Clip not found.")
    return get_clip(clip_id)

@app.delete("/api/clips/{clip_id}")
def delete_clip(clip_id: str):
    with db() as c: row = c.execute("SELECT * FROM clips WHERE id=?", (clip_id,)).fetchone()
    if not row: raise HTTPException(404, "Clip not found.")
    folder = Path(row["vertical_path"] or row["landscape_path"]).resolve().parent
    if not folder.is_relative_to((DATA_DIR / "clips").resolve()): raise HTTPException(400, "Invalid clip path.")
    shutil.rmtree(folder, ignore_errors=True)
    with db() as c: c.execute("DELETE FROM clips WHERE id=?", (clip_id,))
    return {"ok": True}

def clip_file(clip_id: str, fmt: str):
    if fmt not in {"vertical", "landscape"}: raise HTTPException(400, "Format must be vertical or landscape.")
    with db() as c: row = c.execute("SELECT * FROM clips WHERE id=? AND status='complete'", (clip_id,)).fetchone()
    if not row: raise HTTPException(404, "Clip not found.")
    return safe_path(row["vertical_path" if fmt == "vertical" else "landscape_path"])

@app.get("/api/clips/{clip_id}/thumbnail")
def thumbnail(clip_id: str):
    with db() as c: row = c.execute("SELECT thumbnail_path FROM clips WHERE id=? AND status='complete'", (clip_id,)).fetchone()
    if not row: raise HTTPException(404, "Clip not found.")
    return FileResponse(safe_path(row[0]), media_type="image/jpeg")

@app.get("/api/clips/{clip_id}/stream")
def stream_clip(clip_id: str, request: Request, format: str = "vertical"):
    path = clip_file(clip_id, format)
    size = path.stat().st_size
    range_header = request.headers.get("range")
    if not range_header: return FileResponse(path, media_type="video/mp4", headers={"Accept-Ranges": "bytes"})
    match = re.match(r"bytes=(\d*)-(\d*)", range_header)
    if not match: raise HTTPException(416, "Invalid range.")
    start = int(match.group(1) or 0); end = int(match.group(2) or size - 1)
    if start >= size or end < start: raise HTTPException(416, "Range not satisfiable.")
    end = min(end, size - 1)
    def iterator():
        with path.open("rb") as f:
            f.seek(start); remaining = end - start + 1
            while remaining:
                data = f.read(min(1024 * 1024, remaining))
                if not data: break
                remaining -= len(data); yield data
    return StreamingResponse(iterator(), status_code=206, media_type="video/mp4", headers={"Content-Range": f"bytes {start}-{end}/{size}", "Accept-Ranges": "bytes", "Content-Length": str(end-start+1)})

@app.get("/api/clips/{clip_id}/download")
def download_clip(clip_id: str, format: str = "vertical"):
    path = clip_file(clip_id, format)
    return FileResponse(path, media_type="video/mp4", filename=path.name)

