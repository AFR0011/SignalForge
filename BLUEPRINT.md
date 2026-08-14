# Blueprint

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Product objective

Provide a secure, reliable, modern CSV-to-MP3 workflow with isolated and fully resource-bounded jobs.

## Active batch

Status: CLOSED
Batch ID: None

Completed batch: `SELECT-ALL-QUEUE-004` (`PASS_WITH_RISKS`).

### Objective

Let a user select the entire imported track list and queue it for download in one request, instead of capping UI and request selection at 20 tracks, while keeping concurrent reservations and byte budgets bounded.

### Facts

- Default `SELECTION_LIMIT` is 20 in `app.py`, and the browser reads that cap from `data-selection-limit`.
- `templates/index.html` and `static/app.js` treat Select-all / master-checkbox as “first N” and reject larger selections client-side.
- `/download` and `/retry-failed` also apply `SELECTION_LIMIT`; retry currently slices failed tracks to that cap.
- `reserve_indices` still admits a whole request or rejects it. `MAX_ACTIVE_TASKS_PER_JOB` defaults to 8 and each admitted task reserves `TASK_BYTE_RESERVATION` (100 MB) against `MAX_JOB_BYTES` (500 MB), so a large all-at-once reservation would fail even after the 20-track cap is removed.
- CSV import remains bounded at 2,000 rows. Tests override `SELECTION_LIMIT` to 2.

### Assumptions

- “Select all and queue them” means one submit of the imported list, with work starting as task/byte capacity frees, not raising concurrent media workers or disk ceilings.
- Direct `reserve_indices` callers keep all-or-nothing admission for the set they pass.
- Pending indices occupy no byte reservation until admitted.

### Unknowns

- Live populated-browser behavior of a long queue remains unverified, as in prior cycles.

### Intended files

- `app.py`
- `static/app.js`
- `templates/index.html`
- `tests/test_app.py`
- `README.md`
- `DEV_LOG.md` for append-only executor evidence

### Allowed-adjacent files

- Workflow surfaces updated only during PLAN/QA/CLOSE: `BLUEPRINT.md`, `DEV_STATE.md`, `QA_REPORT.md`, `RISK_REGISTER.md`, `docs/PROJECT_STATE.md`, `docs/VERSION_LOG.md`, `docs/ARCHITECTURE.md`, `docs/RUN_PROTOCOL.md`, `docs/TEST_STRATEGY.md`, `docs/REPO_MAP.md`, `shared/*`.

### Out of scope

- Raising `GLOBAL_CONCURRENCY`, `MAX_JOB_BYTES`, `MAX_TOTAL_JOB_BYTES`, or CSV row/byte limits.
- Multi-worker coordination, live-media verification, deployment/secret work, and source-selection redesign.
- Rewriting any prior tester verdict.

### Preconditions

- Previous batch `CAPACITY-SUPPLYCHAIN-003` is closed.
- `shared/locks.json` has no conflicting owner.
- No unresolved Critical product blocker for this UI/queue change. `RISK-001` remains external.

### Acceptance criteria

- Default `SELECTION_LIMIT` equals the default CSV row cap (2,000), so an imported list can be selected in one request.
- Select-all and the master checkbox select every imported track up to `SELECTION_LIMIT`; copy no longer says “first 20”.
- `/download` accepts a selection of the full imported list when it is within `SELECTION_LIMIT` and the song count.
- `/retry-failed` queues every current failed track rather than slicing to 20.
- Tracks that cannot reserve immediately are stored as job-local pending (queued, no reservation/thread) and admitted in order when the same job releases a task slot and bytes.
- Immediate reservations still respect `MAX_ACTIVE_TASKS_PER_JOB`, per-job bytes, and process-wide bytes. A request that cannot reserve or pending-queue any track still fails closed before spawn.
- A pending track whose reservation cannot fit remaining retained bytes is failed with a disk-budget error instead of hanging forever.
- Cleanup, CSV replacement, and TTL reaping treat pending the same as queued/active work.
- Existing isolation, CSRF, capacity, and restoration tests remain passing. Historical FAIL/PASS_WITH_RISKS verdicts are preserved.

### Verification

- Focused tests for full-list selection, pending enqueue under the task ceiling, drain after release, never-fit failure, and pending blocking cleanup/TTL.
- `python -m pytest -q` twice.
- `python -m py_compile app.py`, `node --check static/app.js`, `python -m pip check`, `python -m pip_audit -r requirements.txt` when installed, and `git diff --check`.

### Protected inputs

- `.env`, credentials, user CSV/media/runtime data, paths outside `DATA_ROOT`, unrelated refactors, and all prior QA verdict history.

### Risks

- Pending items do not reserve bytes; a later drain can still hit job/process ceilings. Never-fit cases must fail closed.
- Cross-job process-budget stalls may not drain until this job runs another task or request. Residual of RISK-007.
- Long queues still process two media operations at a time; wall-clock duration is not a new capacity hole but is user-visible.

### Rollback

- Revert the intended product files together. Do not restore the 20-track UI cap independently of the pending-queue admission path.

### Evidence required for done

- Intended-file executor report, focused and repeated suite output, syntax/dependency/diff checks, independent TEST verdict, docs-QA reconciliation, and preserved historical evidence.
