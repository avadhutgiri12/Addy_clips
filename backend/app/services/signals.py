"""Low-cost audio/chat spike detection used for VOD and rolling live streams."""
import array
import math
import statistics
import subprocess
from collections import deque
from pathlib import Path

SAMPLE_RATE = 8000
SENSITIVITY_Z = {"relaxed": 2.5, "balanced": 1.8, "sensitive": 1.2}

def audio_levels(path: Path, sample_rate: int = SAMPLE_RATE):
    """Yield (seconds, RMS dBFS) once per second; FFmpeg does the media decode."""
    proc = subprocess.Popen([
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(path), "-vn",
        "-ac", "1", "-ar", str(sample_rate), "-f", "s16le", "pipe:1"
    ], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    assert proc.stdout is not None
    samples_per_second = sample_rate
    second = 0
    try:
        while True:
            raw = proc.stdout.read(samples_per_second * 2)
            if not raw:
                break
            raw = raw[:len(raw) - len(raw) % 2]
            values = array.array("h"); values.frombytes(raw)
            if not values:
                continue
            rms = math.sqrt(sum(value * value for value in values) / len(values))
            dbfs = 20 * math.log10(max(rms / 32768, 1e-6))
            yield second, dbfs
            second += 1
    finally:
        proc.stdout.close()
        code = proc.wait(timeout=120)
        if code:
            raise RuntimeError(f"FFmpeg audio analysis failed with exit code {code}.")

def robust_z(value: float, history: list[float], floor: float = 1.0) -> float:
    if len(history) < 20:
        return 0.0
    median = statistics.median(history)
    mad = statistics.median(abs(v - median) for v in history)
    return (value - median) / max(floor, 1.4826 * mad)

def score_signals(audio_db: float, audio_history: list[float], chat_count: int = 0,
                  chat_history: list[int] | None = None, chat_available: bool = False) -> tuple[float, int]:
    az = robust_z(audio_db, audio_history)
    if chat_available and chat_history is not None:
        cz = robust_z(float(chat_count), [float(x) for x in chat_history], floor=1.0)
        combined = 0.65 * az + 0.35 * cz
    else:
        combined = az
    score = max(0, min(100, round(50 + 15 * combined)))
    return combined, score

def rank_vod_moments(levels: list[tuple[float, float]], duration: float, config: dict,
                     chat_counts: dict[int, int] | None = None) -> list[dict]:
    """Calculate rolling-baseline peaks, rank them, and keep distinct windows."""
    if len(levels) < 21:
        return []
    chat_counts = chat_counts or {}
    audio_history: deque[float] = deque(maxlen=1800)
    chat_history: deque[int] = deque(maxlen=1800)
    scored = []
    chat_available = bool(config.get("chat_available", False))
    for timestamp, dbfs in levels:
        sec = int(timestamp)
        c = int(chat_counts.get(sec, 0))
        combined, score = score_signals(dbfs, list(audio_history), c, list(chat_history), chat_available)
        scored.append((timestamp, combined, score, dbfs, c))
        audio_history.append(dbfs); chat_history.append(c)
    threshold = SENSITIVITY_Z.get(config.get("sensitivity", "balanced"), 1.8)
    peaks = []
    for i in range(1, len(scored) - 1):
        t, z, score, dbfs, chat = scored[i]
        if z < threshold or z < scored[i-1][1] or z <= scored[i+1][1]:
            continue
        if chat_available and chat >= 4:
            category = "Chat reactions and hype spikes"
        else:
            category = "Streamer reactions and emotions"
        peaks.append({"timestamp": t, "score": score, "category": category,
                      "explanation": f"Audio loudness spike ({dbfs:.1f} dBFS)" + (f" with {chat} chat messages" if chat else ""),
                      "audio_evidence": {"rms_dbfs": round(dbfs, 1), "z_score": round(z, 2)},
                      "chat_evidence": {"messages": chat} if chat else None})
    peaks.sort(key=lambda m: (m["score"], m["timestamp"]), reverse=True)
    result = []
    spacing = max(20, int(config.get("duration", 45) * 0.65))
    pre = max(0, int(config.get("pre_roll", 20)))
    post = max(0, int(config.get("post_roll", 8)))
    for peak in peaks:
        if any(abs(peak["timestamp"] - other["timestamp"]) < spacing for other in result):
            continue
        start = max(0.0, peak["timestamp"] - pre)
        end = min(duration, max(peak["timestamp"] + post, start + int(config.get("duration", 45))))
        if end <= start:
            continue
        peak.update({"start": start, "end": end, "title": f"Audio highlight at {int(peak['timestamp']//60):02d}:{int(peak['timestamp']%60):02d}",
                     "description": peak["explanation"], "hashtags": [], "at": peak["timestamp"]})
        result.append(peak)
        if len(result) >= int(config.get("count", 5)):
            break
    return sorted(result, key=lambda m: m["timestamp"])

class LiveHypeDetector:
    def __init__(self, sensitivity="balanced", chat_available=False, cooldown=45, history_seconds=1800):
        self.sensitivity = sensitivity
        self.chat_available = chat_available
        self.cooldown = cooldown
        self.audio = deque(maxlen=history_seconds)
        self.chat = deque(maxlen=history_seconds)
        self.last_trigger = -cooldown

    def observe(self, second: int, audio_db: float, chat_count: int = 0):
        az, score = score_signals(audio_db, list(self.audio), chat_count, list(self.chat), self.chat_available)
        self.audio.append(audio_db); self.chat.append(chat_count)
        if second - self.last_trigger < self.cooldown:
            return None
        if az < SENSITIVITY_Z.get(self.sensitivity, 1.8):
            return None
        self.last_trigger = second
        category = "Chat reactions and hype spikes" if self.chat_available and chat_count >= 4 else "Streamer reactions and emotions"
        return {"timestamp":float(second), "score":score, "category":category,
                "explanation":f"Audio/chat hype spike ({audio_db:.1f} dBFS, {chat_count} chat messages)",
                "audio_evidence":{"rms_dbfs":round(audio_db,1),"z_score":round(az,2)},
                "chat_evidence":{"messages":chat_count} if chat_count else None}

