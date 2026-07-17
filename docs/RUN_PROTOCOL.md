# Run and Verification Protocol

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Principle

Use the lightest check that can disprove a completion claim, then broaden according to risk. Preserve actual output and record unavailable external checks instead of converting them into a pass.

## Environment and setup

- Declared Python runtime: `.python-version` (`3.14.6` in the verified state).
- Production packages: `python -m pip install --requirement requirements.txt`.
- Development/test packages: `python -m pip install --requirement requirements-dev.txt`; this includes production requirements and pytest.
- FFmpeg: validated executable `FFMPEG_PATH` override or the executable supplied by pinned `imageio-ffmpeg`; the repository build no longer downloads an archive.
- Production requires a strong `SECRET_KEY` of at least 32 characters and rejects missing, weak, or placeholder values.
- Runtime files live under configurable `DATA_ROOT`; use disposable storage for tests and never point tests at user/runtime data.

## Confirmed commands

- Build/install: `python -m pip install --requirement requirements.txt` (also the sole operation in `build.sh`).
- Production: `gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:$PORT app:app`.
- Development: `python app.py` (loopback only, debug disabled).
- Full automated suite: `python -m pytest -q`.
- Syntax: `python -m py_compile app.py` and `node --check static/app.js`.
- Dependency consistency/security: `python -m pip check` and `python -m pip_audit -r requirements.txt` when `pip-audit` is installed.
- Patch hygiene: `git diff --check`.

## Verification ladder

1. Review changed files, protected boundaries, and frozen source hashes.
2. Run the smallest focused pytest selection for the changed behavior.
3. Run `python -m pytest -q`; repeat when acceptance requires deterministic confirmation or concurrency/resource behavior changed.
4. Run Python/JavaScript syntax, dependency consistency, vulnerability audit, and diff checks.
5. Confirm no unexpected worktree changes, background processes, or temporary test residue.
6. For release, run a controlled one-worker target-deployment smoke test, live yt-dlp/FFmpeg flow with legally permitted media, and populated-browser accessibility/visual/end-to-end check.

## Current evidence baseline

- Corrective manual-close race selection: 5 passed.
- Source/global/TTL selection: 19 passed.
- Full pytest suite: 58 passed twice (1.06s and 0.82s in the final independent run).
- Python/JavaScript syntax, `pip check`, point-in-time `pip-audit`, and `git diff --check`: pass.
- Frozen product hashes: unchanged across independent testing; no live processes or temporary residue remained.

## Safety boundaries

- Mock external media/network operations in automated tests; use synthetic CSV fixtures and temporary job roots.
- Do not access `.env` values, deployment credentials, protected user media, or production state during ordinary verification.
- Production must use exactly one worker while registry, ownership, capacity, rate, activity, and TTL authority remains process-local.
- `pip-audit` is point-in-time evidence, and exact versions without hashes do not fully establish artifact provenance.
- Record live media, FFmpeg, deployment, populated-browser, source-rights, and secret-rotation checks as unavailable until direct evidence exists.

## Evidence recording

Record actual commands/results and limitations in `QA_REPORT.md`; append executor/tester history to `DEV_LOG.md`; keep unresolved uncertainty in `RISK_REGISTER.md`.
