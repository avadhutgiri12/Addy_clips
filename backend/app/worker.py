import base64, json, os, subprocess, time, uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from .config import DATA_DIR, API_INTERNAL_URL
from .database import db, now
from .services.video import probe
from .services.detection import normalize_moments

def run(cmd):
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=3600)
    if result.returncode: raise RuntimeError((result.stderr or "FFmpeg failed")[-1200:])

def set_job(job_id, stage, progress, status="running", error=None):
    with db() as c: c.execute("UPDATE jobs SET stage=?,progress=?,status=?,error=?,updated_at=? WHERE id=?", (stage, progress, status, error, now(), job_id))

def canceled(job_id):
    with db() as c: row = c.execute("SELECT cancel_requested FROM jobs WHERE id=?", (job_id,)).fetchone()
    return not row or bool(row[0])

def process(job):
    job_id, project_id = job["id"], job["project_id"]
    config = json.loads(job["config_json"])
    with db() as c: project = dict(c.execute("SELECT * FROM projects WHERE id=?", (project_id,)).fetchone())
    source = Path(project["source_path"])
    work = DATA_DIR / "temp" / job_id
    work.mkdir(parents=True, exist_ok=True)
    try:
        set_job(job_id, "Preparing source", 8)
        info = probe(source); duration = info["duration"]
        if duration < 2: raise RuntimeError("Video must be at least two seconds long.")
        if canceled(job_id): return set_job(job_id, "Canceled", 100, "canceled")
        set_job(job_id, "Sampling gameplay frames", 20)
        frames = []
        # A capped, deterministic sampling budget keeps cost and transfer sizes bounded.
        sample_count = min(24, max(4, int(duration / 30)))
        for i in range(sample_count):
            t = max(0.2, min(duration - 0.1, duration * (i + 0.5) / sample_count))
            out = work / f"frame-{i:02d}.jpg"
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(t), "-i", str(source), "-frames:v", "1", "-vf", "scale=640:-2", "-q:v", "5", str(out)])
            frames.append({"time": t, "base64": base64.b64encode(out.read_bytes()).decode("ascii")})
        if canceled(job_id): return set_job(job_id, "Canceled", 100, "canceled")
        set_job(job_id, "Analyzing gameplay", 36)
        ai_config = {"count": config["count"], "categories": config["categories"]}
        response = httpx.post(f"{API_INTERNAL_URL}/api/internal/jobs/{job_id}/analyze", json={"frames": frames, "duration": duration, "config": ai_config, "model": config.get("model")}, timeout=180)
        if response.status_code == 428:
            return set_job(job_id, "Waiting for Gemini key", 36, "waiting_for_key", "The API restarted and cleared its in-memory Gemini key. Re-enter your key to retry.")
        response.raise_for_status()
        moments = response.json().get("moments", [])
        cleaned = normalize_moments(moments, duration, config)
        set_job(job_id, "Generating clips", 48)
        for index, moment in enumerate(cleaned):
            if canceled(job_id): return set_job(job_id, "Canceled", 100, "canceled")
            clip_id = str(uuid.uuid4())
            folder = DATA_DIR / "clips" / project_id / clip_id
            folder.mkdir(parents=True, exist_ok=True)
            clip_seconds = max(1, moment["end"] - moment["start"])
            inp = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(moment["start"]), "-i", str(source), "-t", str(clip_seconds)]
            # Center crop is the explicit fallback until a validated smart-tracking model exists.
            v = folder / "vertical_9_16.mp4"; l = folder / "landscape_16_9.mp4"; thumb = folder / "thumbnail.jpg"
            run(inp + ["-vf", "scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-movflags", "+faststart", str(v)])
            run(inp + ["-vf", "scale=1920:1080:force_original_aspect_ratio=increase,crop=1920:1080", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-c:a", "aac", "-movflags", "+faststart", str(l)])
            run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-ss", str(min(clip_seconds / 2, 3)), "-i", str(v), "-frames:v", "1", "-vf", "scale=360:-2", str(thumb)])
            metadata = {"id": clip_id, "project_id": project_id, "title": moment["title"], "description": moment["description"], "hashtags": moment["hashtags"], "start": moment["start"], "end": moment["end"], "score": moment["score"], "category": moment["category"], "explanation": moment["explanation"], "smart_crop": "center fallback (automatic tracking unavailable)", "caption_status": "No verified transcription provider configured"}
            (folder / "metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
            with db() as c:
                c.execute("INSERT INTO clips(id,project_id,title,description,hashtags_json,start,end,score,category,caption_json,vertical_path,landscape_path,thumbnail_path,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (clip_id, project_id, moment["title"], moment["description"], json.dumps(moment["hashtags"]), moment["start"], moment["end"], moment["score"], moment["category"], json.dumps([]), str(v), str(l), str(thumb), "complete", now(), now()))
            pct = 55 + int(40 * (index + 1) / max(1, len(cleaned)))
            set_job(job_id, f"Rendered clip {index + 1} of {len(cleaned)}", pct)
        set_job(job_id, "Complete", 100, "complete")
    except Exception as exc:
        set_job(job_id, "Failed", 100, "failed", str(exc)[:1800])
    finally:
        import shutil
        shutil.rmtree(work, ignore_errors=True)
        try:
            httpx.post(f"{API_INTERNAL_URL}/api/internal/jobs/{job_id}/release", timeout=8)
        except Exception:
            pass

def main():
    print("Addy Clips worker started", flush=True)
    # Recover claims once at worker startup; never reset a live job on each queue poll.
    with db() as c:
        c.execute("UPDATE jobs SET status='waiting_for_key',stage='Waiting for Gemini key',error='Worker restarted; re-submit Gemini key to resume.',updated_at=? WHERE status='running'", (now(),))
    concurrency = max(1, min(4, int(os.getenv("WORKER_CONCURRENCY", "1"))))
    with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="addy-worker") as pool:
        active = {}
        while True:
            active = {job_id: future for job_id, future in active.items() if not future.done()}
            while len(active) < concurrency:
                with db() as c:
                    row = c.execute("SELECT * FROM jobs WHERE status='queued' ORDER BY created_at LIMIT 1").fetchone()
                    if not row: break
                    claimed = c.execute("UPDATE jobs SET status='running',attempts=attempts+1,updated_at=? WHERE id=? AND status='queued'", (now(), row["id"]))
                    if not claimed.rowcount: continue
                    job = dict(row)
                active[job["id"]] = pool.submit(process, job)
            time.sleep(1 if active else 2)

if __name__ == "__main__": main()

