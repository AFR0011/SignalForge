# Test Strategy

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Test levels

- Unit/state: filename/path normalization, configuration validation, source-size hooks, job registry lifecycle, reservations, accounting, capacity, fake-clock TTL, and failure restoration.
- Route/template: upload/CSV validation, CSRF, selection, status, ownership, cleanup, file, ZIP, rate-limit, error response, and UI/accessibility contracts.
- Integration with mocks: isolated temporary `DATA_ROOT` plus mocked yt-dlp, Requests/artwork, Mutagen/FFmpeg boundaries, background dispatch, Socket.IO room targeting, and concurrent route/registry races.
- Static checks: Python compilation, browser JavaScript syntax, dependency consistency/audit, and patch whitespace.
- Manual/release: populated-browser accessibility/visual/end-to-end flow and controlled one-worker live deployment/media/FFmpeg smoke test.

## Critical behaviors

- Valid CSV renders; malformed, oversized, excessive-row/field, and invalid-selection inputs are rejected before unsafe allocation.
- Background work uses copied immutable state and emits only to the owned opaque-job room.
- Cross-session status/files/ZIP/cleanup/rooms are denied; paths remain directly below `DATA_ROOT` and files must be allowlisted.
- Cleanup and CSV replacement keep the closing job's slot/bytes through deletion, atomically replace/finalize on success, and restore exact coherent accounting on failure.
- Task, artifact, per-job, source, process-global byte, job-count, ZIP/artwork, request, rate, concurrency, and TTL limits are enforced without counter drift or pre-admission side effects.
- Expiry claims only accepting idle jobs; active/reserved/closing/outside-root jobs are not deleted; filesystem deletion runs outside locks.
- Production rejects missing/weak/placeholder secrets and the committed command retains the one-worker process-local invariant.

## Commands

- Full suite: `python -m pytest -q`.
- Python syntax: `python -m py_compile app.py`.
- Browser-script syntax: `node --check static/app.js`.
- Dependency checks: `python -m pip check` and `python -m pip_audit -r requirements.txt` when available.
- Patch hygiene: `git diff --check`.
- Focused selections should use explicit test names/expressions recorded with their output; do not invent a permanent command that is not committed or evidenced.

## Fixtures and isolation

- `tests/conftest.py` creates isolated app/client fixtures and temporary job roots.
- Use only synthetic CSVs: valid required columns, optional metadata, empty cells, Unicode, duplicates, traversal-like values, oversized rows/fields, and malformed quoting.
- Mock all external media/network/artwork/FFmpeg boundaries in automated verification; never download copyrighted media as a test side effect.
- Inject clocks and synchronization barriers/events for deterministic TTL and concurrency races.
- Freeze relevant product hashes around independent tester runs and verify no process or temporary residue afterward.

## Verified baseline

- Final corrective selection: 5 passed.
- Final source/global/TTL selection: 19 passed.
- Complete suite: 58 passed twice (1.06s and 0.82s).
- Supporting syntax, dependency, point-in-time audit, and diff checks passed.

## Coverage gaps

- No CI workflow or supported-runtime matrix is committed.
- No populated-browser end-to-end/visual/accessibility smoke was run against the final state.
- No live yt-dlp/YouTube/iTunes, artwork, FFmpeg conversion, target deployment, load, long-duration, restart, or multi-process test was run.
- Automatic source identity, rights, and provenance are not proven by the automated suite.
- Requirements are exact-version pinned but not hash pinned.

## Release gate

- Preserve all historical tester verdicts and require current focused/full checks to pass with frozen source hashes.
- Deployment owner confirms secret rotation/session invalidation/history containment.
- Run the committed one-worker command in the target environment with a strong rotated secret and validate writable ephemeral storage.
- Complete controlled live-media/FFmpeg and populated-browser checks with legally permitted media.
- Accept or resolve the open source-matching/rights/provenance and residual supply-chain/retention risks documented in `RISK_REGISTER.md`.
