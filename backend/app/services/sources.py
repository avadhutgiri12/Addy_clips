import re
from urllib.parse import urlparse, parse_qs

from .youtube_live import is_youtube_live_url, extract_youtube_video_id

TWITCH_CHANNEL = re.compile(r"^[A-Za-z0-9_]{1,25}$")
YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")


def twitch_source(url: str):
    try:
        parsed = urlparse(url.strip())
        if parsed.scheme not in {"https", "http"} or (parsed.hostname or "").lower() not in {"twitch.tv", "www.twitch.tv", "m.twitch.tv"}:
            return None
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) == 2 and parts[0].lower() == "videos" and parts[1].isdigit():
            return {"source_type": "twitch_vod", "channel": None, "video_id": parts[1]}
        if len(parts) == 1 and TWITCH_CHANNEL.fullmatch(parts[0]) and parts[0].lower() not in {"directory", "downloads", "jobs", "settings", "wallet", "search", "p"}:
            return {"source_type": "twitch_live", "channel": parts[0].lower(), "video_id": None}
        return None
    except Exception:
        return None


def youtube_live_source(url: str):
    """Detect YouTube live stream URLs."""
    try:
        if not is_youtube_live_url(url):
            return None

        video_id = extract_youtube_video_id(url)
        if not video_id:
            return None

        return {
            "source_type": "youtube_live",
            "video_id": video_id,
            "processable": True,
            "media_access": True,
        }
    except Exception:
        return None

