# Contributing to Addy Clips

Thanks for helping improve the local-first clipping studio.

## Before opening a pull request

- Open or find an issue describing the change.
- Keep source access compliant; do not add arbitrary YouTube downloading or protection bypasses.
- Never persist API keys, uploaded videos, or generated media in source control.
- Keep the worker credential-free. AI requests must be mediated by the API process.
- Include focused tests for behavior changes and update documentation.
- Build and run the Docker Compose stack locally before proposing release-facing changes.

## Development

The supported install is Docker Compose. Frontend and backend sources are in `frontend/` and `backend/`. Runtime data is mounted under `data/`.

## Pull requests

Describe user-visible behavior, architecture changes, validation performed, and any known limitations. Avoid including real videos or secrets in screenshots and logs.

