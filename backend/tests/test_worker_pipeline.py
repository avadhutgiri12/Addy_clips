import json
import shutil
import subprocess
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest

from app import database, worker

@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="FFmpeg is required for the local media pipeline check")
def test_worker_renders_persistent_vertical_and_landscape_clips(tmp_path, monkeypatch):
    data = tmp_path / "data"
    for folder in ("clips", "projects", "temp", "database", "logs"):
        (data / folder).mkdir(parents=True)
    monkeypatch.setattr(database, "DB_PATH", data / "database" / "test.sqlite3")
    monkeypatch.setattr(worker, "DATA_DIR", data)
    monkeypatch.setattr(worker, "API_INTERNAL_URL", "http://worker-test")
    database.migrate()

    project_id, job_id = str(uuid.uuid4()), str(uuid.uuid4())
    project_dir = data / "projects" / project_id
    project_dir.mkdir()
    source = project_dir / "source.mp4"
    subprocess.run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-t", "3", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source)], check=True, timeout=60)
    config = {"project_id":project_id,"mode":"vod","count":1,"duration":30,"sensitivity":"balanced","categories":["Action and combat"],"generate_titles":False,"generate_captions":False}
    with database.db() as c:
        c.execute("INSERT INTO projects(id,title,source_title,source_url,source_path,duration,created_at) VALUES(?,?,?,?,?,?,?)", (project_id, "Fixture session", "Fixture session", None, str(source), 3, database.now()))
        c.execute("INSERT INTO jobs VALUES(?,?,?,?,?,?,?,?,?,?,?)", (job_id, project_id, "running", "Queued", 0, json.dumps(config), None, 0, 0, database.now(), database.now()))
    monkeypatch.setattr(worker, "rank_vod_moments", lambda *args: [{"timestamp":1.5,"start":0.0,"end":3.0,"score":91,"category":"Streamer reactions and emotions","title":"Audio highlight","description":"Audio spike","hashtags":[],"explanation":"Audio loudness spike","audio_evidence":{"rms_dbfs":-10}}])
    monkeypatch.setattr(worker, "audio_levels", lambda *args: [(float(i), -40.0) for i in range(25)])
    worker.process({"id":job_id,"project_id":project_id,"config_json":json.dumps(config)})

    with database.db() as c:
        job = c.execute("SELECT status,progress,error FROM jobs WHERE id=?", (job_id,)).fetchone()
        clip = c.execute("SELECT * FROM clips WHERE project_id=?", (project_id,)).fetchone()
    assert tuple(job[:2]) == ("complete", 100), job["error"]
    assert clip is not None
    assert Path(clip["vertical_path"]).is_file() and Path(clip["vertical_path"]).stat().st_size > 0
    assert Path(clip["landscape_path"]).is_file() and Path(clip["landscape_path"]).stat().st_size > 0
    assert Path(clip["thumbnail_path"]).is_file()
    assert json.loads(clip["hashtags_json"]) == []
    saved_meta = json.loads((Path(clip["vertical_path"]).parent / "metadata.json").read_text())
    assert saved_meta["smart_crop"] == "center crop"
