# QA Report

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Current cycle

- Batch: `CAPACITY-SUPPLYCHAIN-003` corrective pass
- Tester verdict: `PASS_WITH_RISKS`
- Closure recommendation: `COMPLETE_WITH_RISKS`
- Evidence basis: final independent tester run against frozen product sources, reconciled on 2026-07-18.

The corrective batch meets its accepted automated criteria. This verdict does not verify deployment-owner secret rotation, live media services, a deployed production instance, multi-worker operation, or a populated-browser end-to-end flow.

## Verdict history

- `SECURE-JOB-ISOLATION-001`: `FAIL`. The independent lifecycle/resource failure remains historical fact.
- `RESOURCE-ATOMICITY-002`: `PASS_WITH_RISKS`. The corrective lifecycle/resource batch passed 34 tests twice, with residual capacity and external-verification risks.
- `CAPACITY-SUPPLYCHAIN-003` initial implementation: `FAIL`. Manual cleanup and CSV replacement released global capacity before deletion completed.
- `CAPACITY-SUPPLYCHAIN-003` manual-close corrective pass: `PASS_WITH_RISKS`. The closing job now retains its slot and byte accounting until deletion and atomic replacement/finalization complete.

No earlier `FAIL` or `PASS_WITH_RISKS` verdict is superseded or rewritten.

## Acceptance evidence

| Acceptance area | Independent evidence | Result |
| --- | --- | --- |
| Manual cleanup/upload closing-capacity race, exact restoration, and atomic replacement | Focused corrective selection: 5 passed | Pass |
| Positive capacity/source/TTL configuration; yt-dlp source cap; atomic job/global-byte ceilings; TTL safety and restoration | Focused source/global/TTL selection: 19 passed | Pass |
| Existing isolated-job, route, resource, and regression behavior | Full `python -m pytest -q`: 58 passed in 1.06s; repeated: 58 passed in 0.82s | Pass |
| Python and browser-script syntax | `python -m py_compile app.py`; `node --check static/app.js` | Pass |
| Installed dependency consistency | `python -m pip check` | Pass |
| Audited Python dependency set | `python -m pip_audit -r requirements.txt`; no known vulnerabilities reported; `python-dotenv==1.2.2` confirmed | Pass at audit time |
| Patch hygiene | `git diff --check` | Pass |
| Tester isolation and worktree side effects | Frozen source hashes unchanged; no unexpected product changes, live processes, or temporary residue after testing | Pass |
| Exposed remote branch containment | `localUseOnly` remote branch absent | Pass for branch removal only |

## Acceptance mapping

- Positive `MAX_SOURCE_BYTES`, `MAX_JOBS`, `MAX_TOTAL_JOB_BYTES`, and `JOB_TTL_SECONDS` enforcement is covered by the focused 19-test selection and the repeated full suite.
- yt-dlp `max_filesize`, equality/overflow behavior, confined output cleanup, and reservation release are covered by the focused source tests and repeated full suite.
- Atomic process-wide job and retained-plus-reserved byte ceilings, pre-creation refusal, and accounting reconciliation are covered by the focused source/global/TTL tests.
- Fake-clock TTL eligibility, active/reserved/path-invalid exclusions, deletion outside locks, and failed-reap restoration are covered by the focused source/global/TTL tests.
- The original manual-close defect is specifically covered by the five-test corrective selection: paused deletion retains capacity, concurrent creation is refused, deletion/allocation failure restores exact accounting, and successful replacement is atomic.
- Deterministic concurrency tests completed without deadlock and the complete suite passed twice.
- `python-dotenv==1.2.2`, dependency consistency, and the point-in-time vulnerability audit satisfy the accepted dependency-remediation criterion.
- README behavior documentation and single-process scope remained in the frozen source set and the full suite passed twice.

## Residual risks and unavailable checks

- `RISK-001` remains open High and external: the remote branch is absent and production secret validation fails closed, but deployment-owner rotation, session invalidation, confirmation of non-use, and reachable-history purge were not verified.
- Job ownership, rate limits, registry capacity, activity clocks, and TTL accounting are process-local. The committed one-worker topology is required; multi-worker behavior is unsupported and unverified.
- Requirements are exact-version pinned but not hash pinned. `pip-audit` is point-in-time evidence, not a guarantee against later advisories or artifact substitution.
- No live yt-dlp, YouTube/iTunes, artwork, FFmpeg media conversion, or deployed production verification was run. A deployment owner must run a controlled smoke test with legally permitted media.
- No populated-browser end-to-end or visual/accessibility smoke test was run. Automated template/UI contracts and JavaScript syntax passed, but a human browser check remains.
- Automatic source selection can still choose mismatched media; rights and provenance review remains a product/legal responsibility (`RISK-012`).

## Historical bootstrap validation

- Initial structural audit: `PASS_WITH_WARNINGS`; semantic reconciliation completed afterward.
- Bootstrap handoff: `STOP_NEEDS_HUMAN` because a reachable remote branch tracked `.env` with a `SECRET_KEY` variable. This historical stop is preserved.
- Historical read-only checks found Eventlet/runtime and template failures in the original application. Later batches replaced the production worker stack and template behavior; the historical findings are not deleted.
