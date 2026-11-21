# Addy Clips

Addy Clips is a local-first GTA VI clipping studio. The project starts with a Next.js dashboard and a Python FastAPI service. The dashboard captures clip preferences and sends source jobs to the local API; job data, uploaded source videos, settings, and future exports live under `backend/` on this computer.

## Current implementation

- Next.js 16 dashboard with YouTube and live-stream modes, upload drop zone, clip preferences, recent jobs, and Gemini settings UI.
- FastAPI local API for health, Gemini key configuration, job creation/listing, and uploaded source storage.
- Job settings include count, 15–60 second duration, 9:16 or 16:9 framing, source resolution, and a moment prompt.
- The API binds to loopback by default when run with the commands below.

The job API currently queues jobs but does not yet analyze video, monitor YouTube chat, generate captions, or render clips. Those capabilities are staged for the next implementation phases. The dashboard labels this state so it does not imply clips have already been processed.

## Requirements

- Node.js 20.9 or later and npm
- Python 3.11 or later
- FFmpeg (planned for the media-processing phase; not yet called by the current backend)
- A Gemini API key for AI features (the key configuration endpoint is in place; Gemini calls are not yet connected)

## Run locally

In one terminal, start the API:

```powershell
cd backend
py -m venv .venv
.venv\Scripts\Activate.ps1
py -m pip install -r requirements.txt
py -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

In another terminal, start the dashboard from the project root:

```powershell
npm install
npm run dev
```

Open http://localhost:3000. The API docs are at http://127.0.0.1:8000/docs.

Set `NEXT_PUBLIC_API_URL` if the API uses a different local port. The default is `http://127.0.0.1:8000`.

## Local data

The API creates `backend/data/`, `backend/uploads/`, and `backend/output/`. These folders are ignored by Git. `settings.json` holds the Gemini key as local plaintext at this stage; use this only on a trusted local computer. Key encryption and a tighter local origin policy are part of the hardening phase.

## Notes on sources

YouTube stream and video access depends on source availability and platform restrictions. The live mode will need a reliable video and chat ingestion path before automatic spike clipping can be considered complete. Avoid using content you do not have permission to process or redistribute.
