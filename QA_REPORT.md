# QA Report

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Current cycle

- Batch: `SELECT-ALL-QUEUE-004`
- Tester verdict: `PASS_WITH_RISKS`
- Closure recommendation: `COMPLETE_WITH_RISKS`
- Evidence basis: independent TEST against frozen product sources on 2026-08-14.

The batch meets its accepted automated criteria: the imported list can be selected and queued in one request, pending work drains as reservations free, and never-fit/disk-budget cases fail closed. This verdict does not verify deployment-owner secret rotation, live media services, a deployed production instance, multi-worker operation, or a populated-browser end-to-end flow.

## Verdict history

- `SECURE-JOB-ISOLATION-001`: `FAIL`. The independent lifecycle/resource failure remains historical fact.
- `RESOURCE-ATOMICITY-002`: `PASS_WITH_RISKS`. The corrective lifecycle/resource batch passed 34 tests twice, with residual capacity and external-verification risks.
- `CAPACITY-SUPPLYCHAIN-003` initial implementation: `FAIL`. Manual cleanup and CSV replacement released global capacity before deletion completed.
- `CAPACITY-SUPPLYCHAIN-003` manual-close corrective pass: `PASS_WITH_RISKS`. The closing job now retains its slot and byte accounting until deletion and atomic replacement/finalization complete.
- `SELECT-ALL-QUEUE-004`: `PASS_WITH_RISKS`. Full-list selection and bounded pending queue passed focused and repeated automated verification.

No earlier `FAIL` or `PASS_WITH_RISKS` verdict is superseded or rewritten.

## Acceptance evidence

| Acceptance area | Independent evidence | Result |
| --- | --- | --- |
| Full-list selection, pending enqueue, drain, never-fit failure, pending cleanup/TTL | Focused selection: 13 passed, 49 deselected in 0.49s | Pass |
| Existing isolation, route, resource, and regression behavior plus new queue tests | Full `python -m pytest -q`: 62 passed in 1.49s; repeated: 62 passed in 1.36s | Pass |
| Python and browser-script syntax | `python -m py_compile app.py`; `node --check static/app.js` | Pass |
| Installed dependency consistency | `python -m pip check` | Pass |
| Audited Python dependency set | `python -m pip_audit -r requirements.txt` unavailable (`No module named pip_audit`) | Unavailable; residual of RISK-008 |
| Patch hygiene | `git diff --check` | Pass |
| Tester isolation and worktree side effects | Frozen source hashes unchanged after TEST; no product repair during verification | Pass |

## Acceptance mapping

- Default `SELECTION_LIMIT` is 2,000, matching the default CSV row cap. Select-all copy and controls no longer say “first 20”.
- `/download` accepts the full imported list within `SELECTION_LIMIT` and song count; `/retry-failed` no longer slices failed tracks to 20.
- Task-ceiling selections reserve a prefix and pending-queue the remainder; drain after release starts the next pending index.
- Immediate reservations still honor per-job task, per-job byte, and process-wide byte ceilings. Direct `reserve_indices` remains all-or-nothing.
- Pending tracks that cannot fit remaining retained bytes fail with a disk-budget error. Cleanup and TTL treat pending as outstanding work.
- Historical FAIL/PASS_WITH_RISKS verdicts remain recorded above.

## Residual risks and unavailable checks

- `RISK-001` remains open High and external: the remote branch is absent and production secret validation fails closed, but deployment-owner rotation, session invalidation, confirmation of non-use, and reachable-history purge were not verified.
- Job ownership, rate limits, registry capacity, activity clocks, TTL, and pending drain are process-local. The committed one-worker topology is required; multi-worker behavior is unsupported and unverified.
- Pending items do not reserve bytes until admitted. A later drain can still hit job/process ceilings; never-fit cases fail closed. Cross-job process-budget stalls may wait until this job completes other work or receives another queue request (RISK-007 residual).
- Requirements are exact-version pinned but not hash pinned. `pip-audit` was unavailable in this TEST environment.
- No live yt-dlp, YouTube/iTunes, artwork, FFmpeg media conversion, or deployed production verification was run.
- No populated-browser end-to-end or visual/accessibility smoke test was run. Automated template/UI contracts and JavaScript syntax passed, but a human browser check remains.
- Automatic source selection can still choose mismatched media; rights and provenance review remains a product/legal responsibility (`RISK-012`).

## Historical bootstrap validation

- Initial structural audit: `PASS_WITH_WARNINGS`; semantic reconciliation completed afterward.
- Bootstrap handoff: `STOP_NEEDS_HUMAN` because a reachable remote branch tracked `.env` with a `SECRET_KEY` variable. This historical stop is preserved.
- Historical read-only checks found Eventlet/runtime and template failures in the original application. Later batches replaced the production worker stack and template behavior; the historical findings are not deleted.
