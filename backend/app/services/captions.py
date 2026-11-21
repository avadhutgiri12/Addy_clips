"""Optional local speech transcription. The model is loaded only when requested."""
import os
from functools import lru_cache
from pathlib import Path

@lru_cache(maxsize=2)
def _model(name: str, model_dir: str):
    from faster_whisper import WhisperModel
    return WhisperModel(name, device="cpu", compute_type="int8", download_root=model_dir)

def transcribe(path: Path, model_dir: Path) -> list[dict]:
    model_dir.mkdir(parents=True, exist_ok=True)
    try:
        model = _model(os.getenv("WHISPER_MODEL", "base"), str(model_dir))
    except ImportError as exc:
        raise RuntimeError("Optional captions require the worker image with faster-whisper installed.") from exc
    segments, _ = model.transcribe(str(path), word_timestamps=False, vad_filter=True)
    return [{"start": float(s.start), "end": float(s.end), "text": s.text.strip()} for s in segments if s.text.strip()]

def write_srt(segments: list[dict], destination: Path):
    def stamp(seconds):
        ms = max(0, round(seconds * 1000)); h, ms = divmod(ms, 3_600_000); m, ms = divmod(ms, 60_000); s, ms = divmod(ms, 1000)
        return f"{h:02}:{m:02}:{s:02},{ms:03}"
    destination.write_text("\n\n".join(f"{i}\n{stamp(x['start'])} --> {stamp(x['end'])}\n{x['text']}" for i, x in enumerate(segments, 1)), encoding="utf-8")
