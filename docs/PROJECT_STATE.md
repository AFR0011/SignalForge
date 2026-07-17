# Project State

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Objective

Provide a secure, reliable CSV-to-MP3 workflow with isolated and resource-bounded jobs.

## Current status

`CAPACITY-SUPPLYCHAIN-003` is closed `COMPLETE_WITH_RISKS` after the final independent corrective verdict `PASS_WITH_RISKS`. The five focused manual-close race tests, nineteen focused source/global/TTL tests, and the full 58-test suite passed; the full suite passed twice. Syntax, dependency, vulnerability-audit, and diff checks also passed with frozen product hashes unchanged and no tester residue.

Historical verdicts remain authoritative: `SECURE-JOB-ISOLATION-001` `FAIL`; `RESOURCE-ATOMICITY-002` `PASS_WITH_RISKS`; initial `CAPACITY-SUPPLYCHAIN-003` `FAIL`; corrective `CAPACITY-SUPPLYCHAIN-003` `PASS_WITH_RISKS`.

## Stable facts

- The application uses opaque isolated jobs, per-job authorization/CSRF/Socket.IO rooms, bounded in-memory CSV parsing, confined per-job storage, and deterministic cleanup/restoration behavior.
- Source bytes, tasks, per-job retained bytes, total process bytes, process job count, ZIP input, requests, and idle-job lifetime are bounded and covered by deterministic automated tests.
- Manual cleanup and CSV replacement retain closing-job slot/byte accounting through deletion and transition atomically on success; failure restores coherent accounting.
- Production is intentionally one Gunicorn `gthread` worker because job ownership, progress, rate limits, capacity, activity clocks, and TTL accounting are process-local.
- Python dependencies are exact-version pinned. `python-dotenv==1.2.2`; independent `pip check` and point-in-time `pip-audit` passed.

## Open risks and limitations

- The historical secret exposure remains an open High external risk. The remote branch is absent and production secret validation fails closed, but deployment-owner rotation, session invalidation, confirmation of non-use, and reachable-history purge are unverified.
- Automatic source matching, rights, and provenance remain an open Medium product/legal risk.
- Package versions are pinned but hashes are not; the vulnerability audit is point-in-time evidence.
- Live yt-dlp/YouTube/iTunes, artwork, FFmpeg, target deployment, and populated-browser end-to-end behavior were not verified.
- Process-local authority cannot be scaled to multiple workers without shared durable coordination.

## Next milestone

No new batch is active. Before release, the deployment owner must complete the external security actions and controlled one-worker deployment/live-media/FFmpeg/populated-browser checks. Future bounded work may add hash locking, CI/runtime-matrix coverage, durable multi-worker coordination, and source/provenance review.
