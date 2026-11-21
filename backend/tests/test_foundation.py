import json
from fastapi.testclient import TestClient
from app.services.youtube import video_id
from app.services.detection import normalize_moments
from app import database, main
from app.main import app

def test_youtube_urls_only_accept_video_ids():
    assert video_id("https://www.youtube.com/watch?v=abcdefghijk") == "abcdefghijk"
    assert video_id("https://youtu.be/abcdefghijk?t=40") == "abcdefghijk"
    assert video_id("https://youtube.com/live/abcdefghijk") == "abcdefghijk"
    assert video_id("https://youtube.com.evil.example/watch?v=abcdefghijk") is None
    assert video_id("https://example.com/watch?v=abcdefghijk") is None

def test_moment_normalization_scores_deduplicates_and_keeps_pre_event_buffer():
    config = {"sensitivity":"balanced", "duration":45, "count":5,
              "categories":["Action and combat", "Funny moments and fails"]}
    moments = [
        {"timestamp":50,"score":92,"category":"Action and combat","title":"Chase"},
        {"timestamp":55,"score":99,"category":"Action and combat","title":"Duplicate"},
        {"timestamp":110,"score":75,"category":"Funny moments and fails","title":"Unexpected fail"},
        {"timestamp":180,"score":20,"category":"Action and combat","title":"Low signal"},
        {"timestamp":90,"score":80,"category":"Not enabled","title":"Unselected"},
    ]
    result = normalize_moments(moments, 200, config)
    assert [m["title"] for m in result] == ["Chase", "Unexpected fail"]
    assert result[0]["start"] == 30
    assert result[0]["end"] == 75

def test_pre_event_window_clamps_at_source_start():
    result = normalize_moments([{"timestamp": 8, "score": 80, "category": "Action and combat"}], 60,
        {"sensitivity":"balanced", "duration":30, "count":1, "categories":["Action and combat"]})
    assert result[0]["start"] == 0

def test_api_health_and_youtube_metadata_boundary():
    with TestClient(app) as client:
        assert client.get("/api/health").json()["app"] == "Addy Clips"
        response = client.post("/api/source/validate", json={"url":"https://youtu.be/abcdefghijk"})
        assert response.status_code == 200
        payload = response.json()
        assert payload["valid"] is True
        assert payload["media_access"] is False

def test_local_source_stream_supports_http_ranges(tmp_path, monkeypatch):
    data = tmp_path / "data"
    projects = data / "projects"; projects.mkdir(parents=True)
    (data / "database").mkdir()
    monkeypatch.setattr(main, "DATA_DIR", data)
    monkeypatch.setattr(database, "DB_PATH", data / "database.sqlite3")
    database.migrate()
    source = projects / "source.mp4"
    source.write_bytes(b"0123456789")
    with database.db() as c:
        c.execute("INSERT INTO projects VALUES(?,?,?,?,?,?,?)", ("range-project", "Range fixture", "Range fixture", None, str(source), 1, database.now()))
    with TestClient(app) as client:
        response = client.get("/api/projects/range-project/source", headers={"Range":"bytes=2-5"})
        assert response.status_code == 206
        assert response.headers["content-range"] == "bytes 2-5/10"
        assert response.content == b"2345"

