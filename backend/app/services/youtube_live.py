import os
import subprocess
import threading
import time
from collections import deque
from pathlib import Path
from typing import Callable, Optional

from .video import probe


def download_youtube_live(
    url: str,
    output_dir: Path,
    duration_minutes: int = 20,
    progress_callback: Optional[Callable[[int, str], None]] = None,
    cancel_check: Optional[Callable[[], bool]] = None,
) -> Path:
    """
    Download a YouTube livestream using yt-dlp.

    Strategy:
    1. Check if stream is live or ended
    2. For live streams: download from start with --live-from-start
    3. For ended streams: try --download-sections for last N minutes first
    4. If --download-sections fails (YouTube serves live-style URLs), fall back to --live-from-start
    5. After download, trim to last N minutes if file is longer than target

    Args:
        url: YouTube live stream URL
        output_dir: Directory to save the downloaded file
        duration_minutes: Target duration in minutes (for trimming after download)
        progress_callback: Called with (progress_percent, status_message)
        cancel_check: Function that returns True if download should be cancelled

    Returns:
        Path to the downloaded video file (trimmed to duration_minutes if possible)

    Raises:
        RuntimeError: If download fails or is cancelled
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate output filename template
    output_template = str(output_dir / "youtube_live_%(id)s.%(ext)s")

    # First, check if stream is live or ended by probing with yt-dlp
    is_live, stream_duration = _check_if_stream_live(url)

    # Determine download strategy
    # For very long streams (> 2 hours), --download-sections won't work with live-style URLs
    # and --live-from-start takes too long. We'll use --live-from-start with a timeout.
    max_reasonable_duration = 7200  # 2 hours

    if is_live:
        # Live stream: must download from start with --live-from-start
        cmd = _build_cmd_live(url, output_template)
        use_fallback = False
    elif stream_duration and stream_duration > max_reasonable_duration:
        # Very long ended stream: --download-sections fails, --live-from-start takes too long
        # Use --live-from-start with a reasonable timeout (user gets beginning of stream)
        cmd = _build_cmd_live(url, output_template)
        use_fallback = False
        if progress_callback:
            progress_callback(0, f"Stream is {stream_duration//3600}h {(stream_duration%3600)//60}m long. Downloading from start (timeout: 15 min)...")
    else:
        # Shorter ended stream: try --download-sections first for last N minutes
        cmd = _build_cmd_vod_sections(url, output_template, duration_minutes)
        use_fallback = True

    if progress_callback and not (stream_duration and stream_duration > max_reasonable_duration):
        progress_callback(0, "Starting download...")

    # Track the output file path
    downloaded_file: Optional[Path] = None
    download_complete = threading.Event()
    download_error: Optional[Exception] = None
    output_tail = deque(maxlen=20)
    fallback_used = False

    def run_download(cmd_to_use: list[str]):
        nonlocal downloaded_file, download_error
        try:
            process = subprocess.Popen(
                cmd_to_use,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
            )

            # Monitor progress from yt-dlp output
            last_progress = 0
            for line in iter(process.stdout.readline, ''):
                line = line.strip()
                if line:
                    output_tail.append(line)
                if cancel_check and cancel_check():
                    process.terminate()
                    process.wait(timeout=10)
                    raise RuntimeError("Download cancelled by user")

                # Parse progress from yt-dlp output
                # Format: "[download]  45.2% of 123.45MiB at 2.34MiB/s ETA 00:30"
                if "[download]" in line and "%" in line:
                    try:
                        parts = line.split()
                        for i, part in enumerate(parts):
                            if "%" in part and part.replace("%", "").replace(".", "").isdigit():
                                progress = float(part.replace("%", ""))
                                if progress != last_progress:
                                    last_progress = progress
                                    # Scale to 0-30% range for download phase
                                    scaled = int(progress * 0.3)
                                    if progress_callback:
                                        progress_callback(scaled, f"Downloading stream... {progress:.1f}%")
                                break
                    except (ValueError, IndexError):
                        pass

                # Detect when file is created
                if "Destination:" in line:
                    try:
                        dest = line.split("Destination:")[1].strip()
                        downloaded_file = Path(dest)
                    except (IndexError, ValueError):
                        pass

            return_code = process.wait()
            if return_code != 0:
                details = "\n".join(output_tail)
                # Keep diagnostic details while avoiding copying the complete
                # share URL into the persisted job error.
                import re
                details = re.sub(r"https?://\S+", "[source URL]", details)
                raise RuntimeError(f"yt-dlp exited with code {return_code}" + (f":\n{details}" if details else ". Check the worker logs for more information."))

            # If we didn't catch the destination, find the downloaded file
            if not downloaded_file or not downloaded_file.exists():
                files = list(output_dir.glob("youtube_live_*.mp4"))
                if files:
                    downloaded_file = max(files, key=lambda f: f.stat().st_mtime)

            if not downloaded_file or not downloaded_file.exists():
                raise RuntimeError("Download completed but output file not found")

            if progress_callback:
                progress_callback(30, "Download complete, verifying file...")

            # Verify the file is valid
            info = probe(downloaded_file)
            if info["duration"] <= 0:
                raise RuntimeError("Downloaded file has zero duration")

            # If file is longer than target duration, trim to last N minutes
            target_seconds = duration_minutes * 60
            if info["duration"] > target_seconds + 10:  # Add 10s buffer
                if progress_callback:
                    progress_callback(32, f"Trimming to last {duration_minutes} minutes...")
                trimmed_file = _trim_to_last_minutes(downloaded_file, duration_minutes)
                if trimmed_file and trimmed_file.exists():
                    downloaded_file.unlink(missing_ok=True)
                    downloaded_file = trimmed_file
                    info = probe(downloaded_file)

            download_complete.set()

        except Exception as e:
            download_error = e
            download_complete.set()

    def _run_with_fallback(cmd_primary: list[str], cmd_fallback: list[str] | None):
        """Run primary command, fall back to fallback command on failure."""
        nonlocal fallback_used
        run_download(cmd_primary)
        if download_error and cmd_fallback and not fallback_used:
            # Primary failed, try fallback
            if progress_callback:
                progress_callback(10, "Primary download failed, trying fallback...")
            fallback_used = True
            download_error = None
            output_tail.clear()
            downloaded_file = None
            run_download(cmd_fallback)

    # Run download in thread to allow cancellation checking
    if use_fallback:
        # For ended streams, try sections first, then fall back to live-from-start
        cmd_fallback = _build_cmd_live(url, output_template)
        download_thread = threading.Thread(target=_run_with_fallback, args=(cmd, cmd_fallback), daemon=True)
    else:
        # For live streams or very long ended streams, just use live-from-start
        download_thread = threading.Thread(target=run_download, args=(cmd,), daemon=True)

    download_thread.start()

    # Wait for completion with periodic cancel checks
    # Use shorter timeout for very long streams (15 min), longer for normal (45 min)
    max_download_seconds = 900 if (stream_duration and stream_duration > max_reasonable_duration) else 2700
    start_time = time.time()

    while download_thread.is_alive():
        download_thread.join(timeout=1.0)
        if cancel_check and cancel_check():
            # The thread will handle the cancellation
            download_thread.join(timeout=15.0)
            # Clean up partial file
            if downloaded_file and downloaded_file.exists():
                try:
                    downloaded_file.unlink()
                except Exception:
                    pass
            raise RuntimeError("Download cancelled by user")

        # Enforce max download time
        if time.time() - start_time > max_download_seconds:
            # Terminate the process - it's taking too long
            pass

    if download_error:
        # Clean up on error
        if downloaded_file and downloaded_file.exists():
            try:
                downloaded_file.unlink()
            except Exception:
                pass
        raise download_error

    if progress_callback:
        progress_callback(30, "Download verified")

    return downloaded_file


def _build_cmd_live(url: str, output_template: str) -> list[str]:
    """Build yt-dlp command for live stream (--live-from-start)."""
    return [
        "yt-dlp",
        "--live-from-start",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        "--no-continue",
        "--no-warnings",
        "--progress",
        "--newline",
        url,
    ]


def _build_cmd_vod_sections(url: str, output_template: str, duration_minutes: int) -> list[str]:
    """Build yt-dlp command for VOD with --download-sections (last N minutes)."""
    return [
        "yt-dlp",
        "-f", "bestvideo+bestaudio/best",
        "--merge-output-format", "mp4",
        "-o", output_template,
        "--no-playlist",
        "--no-continue",
        "--no-warnings",
        "--progress",
        "--newline",
        "--download-sections", f"*-{duration_minutes * 60}",  # Last N minutes
        url,
    ]


def _check_if_stream_live(url: str) -> tuple[bool, Optional[int]]:
    """
    Check if a YouTube stream is currently live and get its duration.
    Returns: (is_live, duration_seconds)
    """
    try:
        result = subprocess.run(
            ["yt-dlp", "--skip-download", "--print", "%(is_live)s,%(duration)s", url],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0:
            output = result.stdout.strip()
            parts = output.split(",")
            is_live = parts[0].lower() in ("true", "1", "yes")
            duration = None
            if len(parts) > 1 and parts[1].isdigit():
                duration = int(parts[1])
            return is_live, duration
    except Exception:
        pass
    # Default to True (safer to use --live-from-start)
    return True, None


def _trim_to_last_minutes(input_file: Path, minutes: int) -> Optional[Path]:
    """Trim video file to last N minutes using ffmpeg."""
    try:
        output_file = input_file.parent / f"{input_file.stem}_trimmed{input_file.suffix}"
        # Use -sseof to seek from end of file (negative = from end)
        cmd = [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-sseof", f"-{minutes * 60}",  # Seek from end
            "-i", str(input_file),
            "-c", "copy",
            "-avoid_negative_ts", "make_zero",
            str(output_file),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
        if result.returncode == 0 and output_file.exists():
            return output_file
    except Exception:
        pass
    return None


def is_youtube_live_url(url: str) -> bool:
    """Check if a URL is a YouTube live stream URL (youtube.com/live/VIDEO_ID only)."""
    from urllib.parse import urlparse

    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()

        # Only youtube.com/live/VIDEO_ID is definitively a live stream URL
        # youtu.be/VIDEO_ID and youtube.com/watch?v=VIDEO_ID could be regular videos
        # and would require YouTube API to check if they're live
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path.startswith("/live/"):
                # youtube.com/live/VIDEO_ID
                path_parts = parsed.path.strip("/").split("/")
                if len(path_parts) >= 2 and len(path_parts[1]) == 11:
                    return True

    except Exception:
        pass
    return False


def extract_youtube_video_id(url: str) -> Optional[str]:
    """Extract video ID from YouTube live stream URL (youtube.com/live/VIDEO_ID)."""
    from urllib.parse import urlparse
    import re

    ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

    try:
        parsed = urlparse(url.strip())
        host = (parsed.hostname or "").lower()

        # Only extract from youtube.com/live/VIDEO_ID
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"}:
            if parsed.path.startswith("/live/"):
                parts = parsed.path.strip("/").split("/")
                if len(parts) >= 2:
                    candidate = parts[1]
                    return candidate if ID_RE.fullmatch(candidate) else None

        return None
    except Exception:
        return None
