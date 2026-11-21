# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**Addy Clips** is a local-first AI gaming video clipping studio. It turns long gameplay recordings into vertical/landscape highlight clips using Gemini Flash for frame analysis. All data (database, exports, source files) stays on the user's machine via Docker Compose.

**Stack:**
- **Frontend:** Next.js 16 (App Router, React 19, Tailwind CSS 4) — single-page dashboard
- **API:** FastAPI 0.165 (Python 3.12) — REST endpoints, job queue, file streaming
- **Worker:** Python process polling SQLite job queue — FFmpeg rendering, frame sampling, AI analysis via internal API
- **Database:** SQLite (WAL mode) — projects, jobs, clips metadata
- **Containerization:** Docker Compose (CPU-only, no external Redis/DB)

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Frontend   │────▶│    API      │◀───▶│   Worker    │
│  (Next.js)  │     │  (FastAPI)  │     │  (Python)   │
└─────────────┘     └─────────────┘     └─────────────┘
                           │                    │
                           ▼                    ▼
                    ┌─────────────┐     ┌─────────────┐
                    │   SQLite    │     │   FFmpeg    │
                    │  (WAL mode) │     │  (render)   │
                    └─────────────┘     └─────────────┘
```

**Key Design Decisions:**
- **SQLite over Redis:** Single-host workload needs restart-safe local jobs without another service
- **Credential boundary:** Gemini keys arrive only at API; job rows contain no credentials. Worker calls internal `/api/internal/jobs/{job_id}/analyze` endpoint; API keeps key in memory and calls Gemini
- **YouTube Data API = metadata only:** No arbitrary video byte access. Local uploads work; future creator-authorized adapter needed for permitted bytes
- **Center-crop fallback:** Explicit until validated smart-tracking model exists (no subject tracking claims)
- **Durable job queue:** Atomic claim/update transactions; worker recovers `running`→`waiting_for_key` on restart

## Data Layout (persisted in `./data/`)

```
data/
├── clips/{project_id}/{clip_id}/
│   ├── vertical_9_16.mp4
│   ├── landscape_16_9.mp4
│   ├── thumbnail.jpg
│   └── metadata.json
├── projects/{project_id}/
│   └── source{.mp4|.mov|...}
├── temp/{job_id}/          # frame samples (cleaned up after job)
├── database/addy-clips.sqlite3
└── logs/
```

## Development Commands

### Docker (primary development workflow)
```bash
# Start all services
docker compose up -d --build

# View logs
docker compose logs -f          # all services
docker compose logs -f api      # API only
docker compose logs -f worker   # Worker only
docker compose logs -f frontend # Frontend only

# Stop services
docker compose down

# Rebuild after changes
docker compose up -d --build
```

### Backend (Python/FastAPI) — run inside container or locally
```bash
# Install deps (if running locally)
cd backend && pip install -r requirements.txt

# Run API locally (from backend/)
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload

# Run worker locally (from backend/)
python -m app.worker

# Run tests
cd backend && python -m pytest           # all tests
cd backend && python -m pytest tests/test_foundation.py -v
cd backend && python -m pytest tests/test_worker_pipeline.py -v
```

### Frontend (Next.js) — run inside container or locally
```bash
# Install deps (if running locally)
cd frontend && npm install

# Dev server (from frontend/)
npm run dev

# Production build
npm run build

# Start production server
npm start
```

### Environment Configuration
Copy `.env.example` to `.env` and adjust:
- `FRONTEND_PORT`, `BACKEND_PORT` — host ports (default 3000, 8000)
- `DATA_DIR` — host data directory (default `./data`)
- `WORKER_CONCURRENCY` — 1-4 (default 1)
- `YOUTUBE_API_KEY` — optional, enables metadata lookup
- `NEXT_PUBLIC_API_URL` — must match backend URL reachable from browser
- `PUID`/`PGID` — Linux host data directory ownership

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/settings/models` | Available Gemini models, YouTube metadata status |
| POST | `/api/settings/test-key` | Validate Gemini API key |
| POST | `/api/source/validate` | Validate YouTube URL, return metadata |
| POST | `/api/source/preview` | Alias for validate |
| POST | `/api/source/local-upload` | Upload local video (multipart) |
| POST | `/api/analysis/start` | Queue analysis job (requires Gemini key) |
| GET | `/api/analysis` | List recent jobs |
| GET | `/api/analysis/{job_id}` | Get job details |
| POST | `/api/analysis/{job_id}/cancel` | Cancel queued/running job |
| POST | `/api/analysis/{job_id}/retry` | Retry failed/waiting job with key |
| POST | `/api/internal/jobs/{job_id}/analyze` | Internal: worker requests AI analysis |
| POST | `/api/internal/jobs/{job_id}/release` | Internal: worker releases key |
| GET | `/api/projects/{project_id}/source` | Stream source video (range support) |
| GET | `/api/clips` | List clips (search, filter, pagination) |
| GET | `/api/clips/{clip_id}` | Get clip metadata |
| PATCH | `/api/clips/{clip_id}` | Update clip title/description/hashtags |
| DELETE | `/api/clips/{clip_id}` | Delete clip and files |
| GET | `/api/clips/{clip_id}/thumbnail` | Get clip thumbnail |
| GET | `/api/clips/{clip_id}/stream` | Stream clip video (range support) |
| GET | `/api/clips/{clip_id}/download` | Download clip MP4 |

## Worker Pipeline Stages

1. **Preparing source** (8%) — FFprobe validation
2. **Sampling gameplay frames** (20%) — Extract up to 24 frames (640px wide, quality 5)
3. **Analyzing gameplay** (36%) — POST frames to internal API endpoint with Gemini key
4. **Generating clips** (48-95%) — FFmpeg render: center-crop 1080×1920 + 1920×1080, H.264 veryfast CRF 22, preserve audio
5. **Complete** (100%) — Persist clip metadata to SQLite

**Cancellation:** Checked between stages via `cancel_requested` flag in jobs table.

## Key Files to Know

### Backend
- `backend/app/main.py` — FastAPI app, all endpoints, job key management
- `backend/app/worker.py` — Worker main loop, job processing pipeline, FFmpeg rendering
- `backend/app/database.py` — SQLite connection, migrations, row helpers
- `backend/app/config.py` — Environment config, data directory setup
- `backend/app/services/ai.py` — Gemini Flash frame analysis
- `backend/app/services/detection.py` — Moment normalization, scoring, deduplication
- `backend/app/services/video.py` — FFprobe wrapper
- `backend/app/services/youtube.py` — YouTube URL parsing, Data API metadata

### Frontend
- `frontend/app/page.tsx` — Single-page dashboard (Dashboard, Processing, My Clips, History, Settings)
- `frontend/app/globals.css` — Tailwind 4 + custom design system (dark theme)
- `frontend/next.config.ts` — Standalone output for Docker

### Tests
- `backend/tests/test_foundation.py` — Unit tests: YouTube URL parsing, moment normalization, API health, range streaming
- `backend/tests/test_worker_pipeline.py` — Integration test: full worker render with fake AI response (requires FFmpeg)

## Common Tasks

### Adding a new API endpoint
1. Add route in `backend/app/main.py`
2. Add schema in `backend/app/schemas.py` if needed
3. Test with `TestClient` in `backend/tests/test_foundation.py`

### Modifying clip rendering
Edit `backend/app/worker.py` → `process()` function, FFmpeg command construction.

### Changing AI prompt or model
Edit `backend/app/services/ai.py` → `analyze_frames()` and `DEFAULT_MODELS`.

### Adjusting moment detection logic
Edit `backend/app/services/detection.py` → `normalize_moments()`.

### Frontend UI changes
Edit `frontend/app/page.tsx` (React components) and `frontend/app/globals.css` (Tailwind + custom CSS variables).

### Database schema changes
1. Update `backend/app/database.py` → `migrate()` function
2. Handle migration logic for existing deployments (SQLite `ALTER TABLE` limitations)

## Testing Notes

- Backend tests use `fastapi.testclient.TestClient` with monkeypatched `DATA_DIR` and `DB_PATH`
- Worker integration test (`test_worker_pipeline.py`) requires FFmpeg and creates real video via `lavfi` testsrc
- Run tests from `backend/` directory: `python -m pytest`

## Operational Notes

- **Ports bind to loopback (127.0.0.1)** by default — not exposed publicly
- **No authentication** — do not expose directly to internet; use reverse proxy + HTTPS + access control
- **Backup:** Stop stack (`docker compose down`), copy entire `data/` directory
- **Gemini key handling:** Stored in browser localStorage, sent to API only for test/analysis, held in API memory, never in SQLite, never sent to worker
- **Worker concurrency:** Capped at 4; increase only when CPU/memory/disk allow

## Troubleshooting

| Issue | Check |
|-------|-------|
| API unavailable | `docker compose logs -f api`; verify `BACKEND_PORT` and `NEXT_PUBLIC_API_URL` |
| Unsupported/corrupt file | Confirm FFmpeg reads it; check `.env` size/duration limits |
| Gemini rejected key | Valid key? Gemini API enabled in Google Cloud project? |
| No clips found | Inspect job error/progress; try higher sensitivity or shorter source |
| Exports slow | CPU encoding; increase `WORKER_CONCURRENCY` if resources allow |
| YouTube metadata only | Expected; upload local file for processing |