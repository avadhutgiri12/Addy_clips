# Addy Clips

**Turn every stream into a highlight.** Addy Clips is a local-first AI gaming video clipping studio. Upload a recording, ask Gemini to inspect a bounded set of sampled frames, and render the resulting moments as vertical and landscape MP4s. Your database and completed exports stay on your machine.

> Current scope: local video analysis and exports are implemented. YouTube metadata lookup is optional; arbitrary YouTube video bytes are not downloaded. Live capture, automatic subject tracking, transcription, and captions are not enabled until supported source/provider adapters are configured.

## Features

- Local MP4, MOV, MKV, WebM, and AVI upload with FFprobe validation.
- Gemini Flash analysis of sampled frames, with grounded title, description, and hashtags (no random timestamps or fabricated evidence).
- Persistent SQLite job queue with worker progress, cancellation, and retry after a lost in-memory key.
- Center-crop fallback exports in 1080×1920 and 1920×1080 H.264, preserving source audio.
- Persistent clip files, searchable clip gallery, metadata editing, streaming with HTTP ranges, and individual downloads.
- Responsive dark production workspace with local browser preferences and no account requirement.
- CPU-only Docker Compose setup; no external database or broker.

`WORKER_CONCURRENCY` defaults to one and can be raised to four after considering available CPU, memory, and disk throughput.

## Screenshots

Screenshots will be added after a release build is available.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md). The frontend is Next.js 16, the API is FastAPI, and a separate Python worker polls a durable SQLite job queue. SQLite was chosen instead of Redis because this single-host workload needs restart-safe local jobs without another service. Gemini keys are held in API memory and excluded from the job record; the worker calls an internal API endpoint for AI analysis and never receives the key.

## Prerequisites

- Git
- Docker Engine or Docker Desktop with Docker Compose V2
- A Gemini API key from [Google AI Studio](https://aistudio.google.com/apikey)
- Recommended: 4 CPU cores, 8 GB RAM, and free disk space at least as large as your source plus exports. Longer 1080p videos can take substantially longer on CPU.

The host does not need Node.js, Python, or FFmpeg.

## Install

```sh
git clone https://github.com/OWNER/addy-clips.git
cd addy-clips
cp .env.example .env
docker compose up -d --build
```

Open <http://localhost:3000>. Ports bind to loopback by default. Configure `FRONTEND_PORT`, `BACKEND_PORT`, `DATA_DIR`, and (on Linux hosts) the data-directory owner IDs `PUID`/`PGID` in `.env` if needed. Keep `NEXT_PUBLIC_API_URL` aligned with the backend URL reachable from your browser.

## Configure Gemini

Open **Settings**, paste your key, test it, and save. The browser stores it in local storage; local storage is convenient but is not a secure vault. The key is sent to your local API when testing or starting an analysis, held in API memory for that job, omitted from SQLite, and never sent to the video worker. Restarting the API clears its in-memory copy; a paused job can be retried by submitting the key again. The model list uses current Flash IDs and can be adjusted in Settings.

The API samples up to 24 frames from each recording. The worker renders clips around the returned timestamps, including up to 20 seconds before the event when available. Frame judgments can miss audio-only reactions. The current renderer uses a reported center-crop fallback; it does not claim subject tracking. Captions are not generated without a transcription provider.

## YouTube limitations

`YOUTUBE_API_KEY` optionally enables official YouTube Data API metadata lookup. Metadata is not video access. The application does not download arbitrary YouTube streams, bypass authentication, DRM, or platform controls. For video processing, upload a local recording or integrate a permitted creator-authorized media source. YouTube live chat is not currently connected, and a live URL alone cannot trigger clipping.

## Process a recording

1. Open Dashboard and choose a local MP4, MOV, MKV, WebM, or AVI recording.
2. Choose clip count, duration, categories, and sensitivity.
3. Save a Gemini key in Settings.
4. Start analysis and follow the persisted worker stage in Processing.
5. Edit a clip title/description, preview either format, or download each MP4 from Generated Clips.

Completed clips are stored at `data/clips/{project_id}/{clip_id}/`. Source files and project intermediates are under `data/projects/`; the SQLite database is under `data/database/`.

## Operations and backup

```sh
docker compose ps
docker compose logs -f
docker compose down
docker compose up -d --build
```

Back up the entire `data/` directory while the stack is stopped, or use a consistent filesystem snapshot. Restore by copying it back before starting Compose. Normal updates and shutdowns do not remove persistent data. Do not expose this no-login application directly to the public internet; use HTTPS, a reverse proxy, and access control for remote use.

## Troubleshooting

- **API unavailable:** `docker compose logs -f api`; check `BACKEND_PORT` and `NEXT_PUBLIC_API_URL`.
- **Unsupported or corrupt file:** confirm FFmpeg can read it and that duration/size are within `.env` limits.
- **Gemini rejected key:** use a valid key and check that Gemini API access is enabled for its Google project.
- **No clips found:** inspect the job error/progress. Frame sampling can miss brief events; try a more sensitive setting or a shorter source segment.
- **Exports take a while:** CPU encoding time depends on duration, resolution, and available cores. Increase worker concurrency only when memory and disk allow it.
- **YouTube says metadata only:** this is expected; upload a local copy you are permitted to process.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). Please open an issue before large architecture changes.

## License

MIT. See [LICENSE](LICENSE).

