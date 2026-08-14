# Repository Profile

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Classification

- Primary type: `software`
- Secondary traits: Flask web application, Flask-SocketIO threading/simple-websocket, media processing, external network services, single-worker Gunicorn deployment, pytest verification
- Confidence: high
- Semantic inventory reconciled: 2026-07-18

## Evidence

- `app.py` defines the Flask application factory, HTTP routes, Socket.IO background work, in-memory process-local job registry, standard-library CSV parsing, and executable development entry point.
- `templates/` and `static/` provide the browser UI.
- `.python-version`, `Procfile`, `build.sh`, `requirements.txt`, and `requirements-dev.txt` define runtime, deployment, build, production dependencies, and test dependencies.
- `tests/conftest.py` and `tests/test_app.py` provide deterministic pytest coverage with mocked live media/network boundaries.
- There are no datasets, models, notebooks, training, or evaluation pipelines.

## Governance and state

- Repository guidance: `AGENTS.md`.
- Active-state authority: `DEV_STATE.md`.
- Accepted batch/criteria authority: `BLUEPRINT.md`.
- Verification and uncertainty: `QA_REPORT.md` and `RISK_REGISTER.md`.
- Current cycle: `SELECT-ALL-QUEUE-004` closed `COMPLETE_WITH_RISKS`; final tester verdict `PASS_WITH_RISKS`.

## Entry points and commands

- Application: `app.py`; browser assets: `static/app.js`, `templates/index.html`.
- Production install: `python -m pip install --requirement requirements.txt`.
- Development/test install: `python -m pip install --requirement requirements-dev.txt`.
- Production: `gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app`.
- Local development: `python app.py` (binds loopback, debug disabled).
- Verification: `python -m pytest -q`, `python -m py_compile app.py`, `node --check static/app.js`, `python -m pip check`, `python -m pip_audit -r requirements.txt`, and `git diff --check` when the audit tool is installed.

## Protected and generated boundaries

### Protected/sensitive

- `.env`, deployment secrets, and all secret values.
- User CSV bytes in request memory and downloaded/tagged media under configured `DATA_ROOT`.
- System temporary ZIP files created for a response.

### Generated/runtime outputs

- Random per-job directories directly below `DATA_ROOT` (default: system temp directory plus `spotifydownautomater`).
- Temporary ZIP response files in the system temp directory; cleanup is registered after response.
- Python/pytest caches and local virtual environments.
- FFmpeg supplied by pinned `imageio-ffmpeg` may use its package-managed binary/cache outside repository source.

## Profile review

- [x] Primary type and traits confirmed by semantic repository mapping.
- [x] Authority, protected paths, generated outputs, and commands reconciled to final implementation.
- [x] Pytest verification path exists; `SELECT-ALL-QUEUE-004` independent full suite passed 62 tests twice.
- [ ] Deployment owner confirmed secret rotation/session invalidation/history containment and target production behavior.
- [ ] Live media/FFmpeg and populated-browser checks completed.
