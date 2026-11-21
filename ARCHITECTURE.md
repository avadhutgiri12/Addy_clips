# Addy Clips architecture

## Implementation plan

1. **Foundation:** establish the Next.js 16 interface, FastAPI modules, Docker services, persistent data layout, health checks, and public repository files.
2. **Sources:** validate YouTube URLs, retrieve official metadata only when configured, and accept local video uploads with FFprobe validation.
3. **Jobs and media:** use a SQLite-backed durable queue polled by one worker; prepare/sample local media, create project-organized permanent exports, and report persisted job state.
4. **AI and moments:** connect a user-supplied Gemini key from the API process for sampled-frame analysis, score/rank non-overlapping moments, and add speech/chat signals only when an actual provider is configured.
5. **Clips and editing:** serve stored video with HTTP ranges, persist metadata edits, and expose preview/download/delete. Add captions and crop refinement behind truthful capability statuses.
6. **Live and release:** add a permitted source adapter before enabling rolling-buffer live processing; verify Docker persistence, security boundaries, and docs.

## Decisions

- **Background work:** SQLite queue with atomic claim/update transactions. This single-host product needs durability and restart recovery, not a broker. A separate worker container polls the queue; configurable concurrency is capped at four. No Redis service is needed.
- **Credential boundary:** Gemini keys arrive only at the API. Job rows contain no credentials. The worker sends sampled media to an internal API analysis endpoint; the API keeps a job's key in memory and calls Gemini. After an API restart, a job requiring AI pauses and asks the user to re-submit credentials. Keys are never logged or put in task messages.
- **Source access:** YouTube Data API metadata is not video access. Processing arbitrary YouTube streams is not implemented. Local uploads work; a future creator-authorized adapter can supply permitted bytes.
- **Live streams:** live capture is disabled until a supported authorized video-byte adapter exists. The 60-second polling cadence alone cannot make inaccessible streams processable.
- **AI scope:** sampled frames are submitted as images to a Gemini Flash model. Audio transcription and chat reaction evidence are optional signals; no fabricated evidence is generated when those providers are absent.
- **Storage:** SQLite metadata lives at `data/database`; project source/intermediates at `data/projects` and `data/temp`; completed clip files at `data/clips/{project_id}/{clip_id}`. Only temporary/intermediate paths are cleanup candidates.

## Operational boundaries

Docker Compose binds ports to loopback by default and persists `./data`. The API and worker share the data mount. CPU-only FFmpeg is supported. A local upload produces a source preview. YouTube metadata requires `YOUTUBE_API_KEY`, but that key is separate from Gemini and does not confer media access.

