# Version Log

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## 2026-07-17 - Governance bootstrap

- Added profile-aware workflow documentation pack.
- No product/source/data/result artifacts intentionally modified.

## 2026-07-17 - SECURE-JOB-ISOLATION-001

- Implemented the first isolated-job security and workflow repair batch.
- Independent verdict: `FAIL`; lifecycle and resource defects remained. This verdict is preserved.

## 2026-07-17 - RESOURCE-ATOMICITY-002

- Added registry-authoritative lifecycle transitions, bounded task/artifact/job resources, atomic reservations, and failure reconciliation.
- Independent verdict: `PASS_WITH_RISKS`; 34 tests passed twice. This verdict is preserved.

## 2026-07-17 - CAPACITY-SUPPLYCHAIN-003 initial implementation

- Added source, global job/byte capacity, idle TTL, and dependency-remediation controls.
- Independent verdict: `FAIL`; manual cleanup and CSV replacement exposed a deletion-time capacity-release race. This verdict is preserved.

## 2026-07-18 - CAPACITY-SUPPLYCHAIN-003 corrective closure

- Retained closing-job capacity through manual deletion and made replacement/finalization an atomic registry transition with exact failure restoration.
- Independent verdict: `PASS_WITH_RISKS` after 5 focused corrective tests, 19 focused source/global/TTL tests, and 58 full tests passed; the full suite passed twice.
- Syntax, dependency consistency, point-in-time vulnerability audit, and diff checks passed. Frozen product hashes were unchanged and testing left no process or temporary residue.
- Workflow state closed `COMPLETE_WITH_RISKS`; external secret rotation/history containment, one-worker deployment/live-media/FFmpeg verification, populated-browser verification, hash locking, and automatic-source provenance remain outstanding.

## 2026-08-14 - SELECT-ALL-QUEUE-004

- Raised the request/UI selection cap to the imported CSV size (default 2,000 rows) and queued overflow tracks in a job-local pending list that drains as reservations free.
- Independent verdict: `PASS_WITH_RISKS` after 13 focused queue tests and 62 full tests passed twice; syntax, `pip check`, and `git diff --check` passed. Frozen product hashes were unchanged. `pip-audit` was unavailable.
- Workflow state closed `COMPLETE_WITH_RISKS`; historical verdicts and external/live-verification actions remain outstanding.
