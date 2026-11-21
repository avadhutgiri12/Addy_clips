import json
import subprocess
from pathlib import Path

def probe(path: Path) -> dict:
    result = subprocess.run(["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)], capture_output=True, text=True, timeout=45)
    if result.returncode:
        raise ValueError("FFprobe could not read this video. Check that the file is a supported video format.")
    data = json.loads(result.stdout)
    video = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    if not video:
        raise ValueError("The selected file does not contain a video stream.")
    fmt = data.get("format", {})
    return {"duration": float(fmt.get("duration") or 0), "width": int(video.get("width") or 0), "height": int(video.get("height") or 0), "format": fmt.get("format_name", "video")}

