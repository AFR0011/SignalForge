# Project State

Workflow schema: `agentic-workflow/v2`
Project: SignalForge
Repository profile: software
Initialized: 2026-07-17

## Objective

Provide a secure, reliable CSV-to-MP3 workflow with isolated and resource-bounded jobs.

## Current status

`PORTFOLIO-FINALIZATION-005` closed `COMPLETE_WITH_RISKS` after a preserved
initial `FAIL` and corrective `PASS_WITH_RISKS`. The independent corrective run
passed all 118 tests, syntax, dependency consistency, publication guard, SVG XML,
protected hashes, internal-path/ignore, diff, documentation-order, and
merged-branch ancestry checks. Product behavior and valid history remained
frozen. Local `pip-audit` is unavailable, while CI installs and runs it.

Historical verdicts remain authoritative: `SECURE-JOB-ISOLATION-001` `FAIL`; `RESOURCE-ATOMICITY-002` `PASS_WITH_RISKS`; initial `CAPACITY-SUPPLYCHAIN-003` `FAIL`; corrective `CAPACITY-SUPPLYCHAIN-003` `PASS_WITH_RISKS`; `SELECT-ALL-QUEUE-004` `PASS_WITH_RISKS`.

## Stable facts

- The application uses opaque isolated jobs, per-job authorization/CSRF/Socket.IO rooms, bounded in-memory CSV parsing, confined per-job storage, and deterministic cleanup/restoration behavior.
- An imported CSV can be selected and queued in one request up to the 2,000-row cap. Concurrent reservations remain bounded; overflow tracks wait in a job-local pending queue and drain as capacity frees.
- Source bytes, tasks, per-job retained bytes, total process bytes, process job count, ZIP input, requests, and idle-job lifetime are bounded and covered by deterministic automated tests.
- Manual cleanup and CSV replacement retain closing-job slot/byte accounting through deletion and transition atomically on success; failure restores coherent accounting. Pending work blocks cleanup and TTL.
- Production is intentionally one Gunicorn `gthread` worker because job ownership, progress, rate limits, capacity, activity clocks, pending drain, and TTL accounting are process-local.
- Python dependencies are exact-version pinned. `python-dotenv==1.2.2`.

## Open risks and limitations

- The historical credential is rotated and inactive, and the affected commit is
  absent from advertised refs and fresh clones. GitHub still serves the
  already-unreferenced object directly, so cached-view removal remains an open
  High external risk.
- Automatic source matching, rights, and provenance remain an open Medium product/legal risk.
- Package versions are pinned but hashes are not; local `pip-audit` is
  unavailable in this cycle and CI audit evidence is point-in-time.
- Live yt-dlp/YouTube/iTunes, artwork, FFmpeg, target deployment, and populated-browser end-to-end behavior were not verified.
- Process-local authority cannot be scaled to multiple workers without shared durable coordination.

## Next milestone

Publish and corroborate the normal descendant commit through public CI and a
fresh clone, then complete the GitHub Support cached-object request. A public
deployment still requires controlled one-worker, live-media/FFmpeg, and full
populated-browser accessibility/end-to-end checks.
