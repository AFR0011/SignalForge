# Repository Map

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Project shape

Profile `software`: a Flask/Flask-SocketIO CSV-to-MP3 web application with a responsive browser UI, external media/artwork adapters, process-local job control, one-worker Gunicorn deployment, and deterministic pytest coverage.

## Top-level inventory

- Product: `app.py`, `templates/`, `static/`, `README.md`.
- Runtime/build/deployment: `.python-version`, `requirements.txt`, `requirements-dev.txt`, `build.sh`, `Procfile`, `.gitignore`.
- Verification: `tests/`.
- Governance: `AGENTS.md`, `BLUEPRINT.md`, `DEV_STATE.md`, `DEV_LOG.md`, `QA_REPORT.md`, `RISK_REGISTER.md`, `docs/`, `shared/`.
- Project metadata: `LICENSE`, `todo.md`, `.gitattributes`.

## Entry points

- Flask application factory/module and local executable: `app.py`.
- Production WSGI target: `app:app` through the committed one-worker Gunicorn `gthread` command.
- Browser entry surfaces: `templates/index.html` and `static/app.js`.
- Test suite: `tests/test_app.py` with `tests/conftest.py`.

## Authoritative inputs

- Product source: `app.py`, `templates/`, and `static/`.
- Runtime/dependency/deployment: `.python-version`, `requirements.txt`, `requirements-dev.txt`, `build.sh`, and `Procfile`.
- Runtime configuration: `SECRET_KEY`, `DATA_ROOT`, `FFMPEG_PATH`, `PORT`, and production-environment detection through `RENDER`/`RENDER_EXTERNAL_URL`; bounded settings may be supplied through Flask configuration for embedding/tests.
- External untrusted input: uploaded CSV requiring `Song` and `Artist`, optionally consuming `Album` and `Genres`; yt-dlp/YouTube and iTunes artwork responses.
- Acceptance and evidence: `BLUEPRINT.md`, `QA_REPORT.md`, and `RISK_REGISTER.md` under the authority order in `AGENTS.md`.

## Generated outputs

- Random per-job directories directly below configured `DATA_ROOT`; they contain only allowlisted downloaded/tagged artifacts and in-memory registry metadata is not persisted.
- Temporary ZIP response files in the system temp directory, scheduled for deletion after response.
- Python/pytest caches and local virtual environments.
- Package-managed FFmpeg binary/cache supplied by pinned `imageio-ffmpeg`, unless a validated `FFMPEG_PATH` override is used.
- Uploaded CSV bytes are parsed in memory and are not written to an upload directory; there is no Flask-Session filesystem store.

## Build/run/verify paths

- Production dependency install: `python -m pip install --requirement requirements.txt`; `build.sh` performs only this command.
- Development/test install: `python -m pip install --requirement requirements-dev.txt`.
- Production: `gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app`.
- Local development: `python app.py` (loopback, debug disabled).
- Automated suite: `python -m pytest -q` (58 tests in the final verified state).
- Supporting checks: `python -m py_compile app.py`, `node --check static/app.js`, `python -m pip check`, `python -m pip_audit -r requirements.txt`, and `git diff --check`.

## Protected and sensitive paths

- `.env` and all deployment secret values.
- Configured `DATA_ROOT` job directories, downloaded media, user listening metadata, and temporary ZIPs.
- External paths outside `DATA_ROOT`; containment logic must refuse them.
- User/deployment credentials and live service state were not accessed during automated verification.

## Ownership

- Repository/deployment owner and maintainers: not confirmed in governance evidence.
- Workflow governance: root session under active `AGENTS.md` scope.
- Job authority at runtime: one process-local registry; exactly one production worker is required.

## Current gaps

- Deployment-owner secret rotation, session invalidation, non-use confirmation, and reachable-history purge remain unverified (`RISK-001`).
- Multi-worker/distributed coordination is unsupported; live deployment/load/long-duration behavior is unverified.
- Dependencies are exact-version pinned but not hash pinned; audit evidence is point-in-time.
- Automatic source matching/rights/provenance, live yt-dlp/FFmpeg, and populated-browser verification remain open limitations.
