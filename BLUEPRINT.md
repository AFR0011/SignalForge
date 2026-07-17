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

Completed batch: `CAPACITY-SUPPLYCHAIN-003` corrective pass (`PASS_WITH_RISKS`).

### Objective

Bound transient downloader writes and total process capacity, safely expire abandoned idle jobs, and remediate the audited python-dotenv vulnerability.

### Historical evidence

- SECURE-JOB-ISOLATION-001 received an independent FAIL for lifecycle and resource defects.
- RESOURCE-ATOMICITY-002 corrected those defects and received PASS_WITH_RISKS after 34 tests passed twice.
- Its residual High availability findings and the subsequent dependency audit drive this final batch; neither historical verdict may be rewritten.
- CAPACITY-SUPPLYCHAIN-003 first independent verification received FAIL: manual cleanup and CSV replacement released global capacity before deletion completed, allowing failed restoration to exceed both process ceilings. This corrective pass must preserve that verdict.

### Intended files

- `app.py`
- `tests/test_app.py`
- `README.md`
- `requirements.txt`
- `DEV_LOG.md` for append-only executor evidence

### Out of scope

- Multi-process or distributed job coordination, durable queues, live-media verification, deployment changes, source-selection redesign, and further UI work.
- Rewriting any prior tester verdict or claiming external secret rotation without evidence.

### Acceptance criteria

- Positive `MAX_SOURCE_BYTES`, `MAX_JOBS`, `MAX_TOTAL_JOB_BYTES`, and `JOB_TTL_SECONDS` configuration is enforced.
- yt-dlp receives `max_filesize`; known total, estimate, or downloaded bytes above the source cap aborts, removes all confined task outputs, and releases reservations.
- Atomic process-wide job and retained-plus-reserved byte ceilings reject before directory or background-task creation and never underflow or drift.
- Opportunistic fake-clock-testable TTL reaping removes only expired accepting idle jobs; active/reserved jobs and outside-root paths are never deleted.
- Failed reap deletion restores the same coherent job and capacity accounting after reconciling surviving files.
- Manual cleanup and CSV replacement also retain the closing job's slot and byte accounting until deletion succeeds, then replace/finalize atomically; concurrent creation cannot steal the slot and failed deletion cannot restore above either cap.
- All multi-lock paths preserve registry-then-job ordering and deterministic concurrency tests terminate without deadlock.
- `python-dotenv==1.2.2` replaces the vulnerable 1.1.1 pin and `pip-audit` reports no known vulnerability.
- Existing behavior remains passing twice with no live media access, and README documents defaults, refusal, expiry, and single-process scope.

### Verification

- Focused capacity/source/reaper tests plus `python -m pytest -q` twice.
- `python -m py_compile app.py`, `node --check static/app.js`, `python -m pip check`, `python -m pip_audit -r requirements.txt`, and `git diff --check`.
- Frozen source hashes around an independent tester run.

### Protected inputs

- `.env`, credentials, user CSV/media/runtime data, paths outside `DATA_ROOT`, unrelated changes, and all prior QA verdict history.

### Rollback

- Revert the capacity/source/reaper implementation, tests, and documentation together. Do not restore the vulnerable dependency pin or unsafe remote branch.

### Evidence required for done

- Intended-file-only executor report, focused and repeated suite output, clean security audit, independent verdict, docs-QA reconciliation, and preserved historical evidence.
