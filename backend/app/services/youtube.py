import re
import httpx
from ..config import YOUTUBE_API_KEY

ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

def video_id(url: str) -> str | None:
    try:
        from urllib.parse import urlparse, parse_qs
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()
        if host in {"youtu.be", "www.youtu.be"}:
            candidate = parsed.path.strip("/").split("/")[0]
        elif host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path == "/watch": candidate = parse_qs(parsed.query).get("v", [""])[0]
            else:
                parts = parsed.path.strip("/").split("/")
                candidate = parts[1] if len(parts) > 1 and parts[0] in {"live", "embed", "shorts"} else ""
        else:
            return None
        return candidate if ID_RE.fullmatch(candidate) else None
    except Exception:
        return None

async def metadata(url: str):
    vid = video_id(url)
    if not vid:
        return None
    result = {"video_id": vid, "valid": True, "media_access": False, "access_message": "YouTube metadata does not grant access to video bytes. Use a local file or a permitted creator-authorized source."}
    if not YOUTUBE_API_KEY:
        result.update({"metadata_available": False, "metadata_message": "Add YOUTUBE_API_KEY to .env to retrieve official video metadata."})
        return result
    async with httpx.AsyncClient(timeout=12) as client:
        response = await client.get("https://www.googleapis.com/youtube/v3/videos", params={"part": "snippet,contentDetails,liveStreamingDetails", "id": vid, "key": YOUTUBE_API_KEY})
        response.raise_for_status()
        items = response.json().get("items", [])
    if not items:
        return {**result, "metadata_available": False, "metadata_message": "No public metadata was returned for this video."}
    item = items[0]
    snippet, detail = item.get("snippet", {}), item.get("contentDetails", {})
    result.update({"metadata_available": True, "title": snippet.get("title"), "channel": snippet.get("channelTitle"), "thumbnail": (snippet.get("thumbnails", {}).get("high") or snippet.get("thumbnails", {}).get("default") or {}).get("url"), "duration": detail.get("duration"), "live": bool(item.get("liveStreamingDetails", {}).get("actualStartTime") and not item.get("liveStreamingDetails", {}).get("actualEndTime")), "access_message": "Metadata retrieved. Video bytes are not available through the YouTube Data API."})
    return result

