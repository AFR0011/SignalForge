# Development Log

Workflow schema: `agentic-workflow/v2`
Project: SignalForge
Repository profile: software
Initialized: 2026-07-17

## 2026-07-17 - Repository bootstrap

- Classified as `software` with Flask, Socket.IO, media-processing, external-network, and deployment traits; semantic confidence is high.
- Created missing governance files without modifying product/source artifacts.
- Classification evidence is recorded in `docs/REPO_PROFILE.md`.
- Reconciled repository map, commands, architecture, test strategy, dependency policy, QA evidence, and thirteen risks.
- Dev-loop stopped before planning or implementation because a live remote branch/history exposes a `SECRET_KEY` variable requiring owner rotation and session invalidation.

## 2026-07-17 - SECURE-JOB-ISOLATION-001 executor evidence

- Replaced shared session/song/download state with a locked process-local registry keyed by opaque random job IDs and confined per-job directories below configurable `DATA_ROOT`.
- Replaced server-side sessions and stored song cookies with a signed cookie containing only `job_id`; mutating HTTP routes validate a stateless per-job HMAC CSRF token.
- Replaced pandas CSV parsing with bounded in-memory standard-library parsing and added request, byte, row, field, selection, concurrency, artifact, ZIP, network-response, path, and rate limits.
- Restricted Socket.IO progress to an ownership-validated job room. Background tasks receive copied job/song values and do not read Flask session state.
- Added ownership and allowlist checks for status, file, ZIP, and cleanup operations. Cleanup is POST-only, active-job guarded, idempotent, and refuses directories outside `DATA_ROOT`.
- Replaced Eventlet deployment with one Gunicorn gthread worker and pinned the accepted runtime packages. `build.sh` now performs only the pinned requirements install; FFmpeg resolves from a validated override or `imageio-ffmpeg`.
- Rebuilt the browser UI as a dependency-free responsive audio workspace with semantic structure, keyboard focus, live messages, drag/drop import, dashboard/queue progress, authoritative file URLs, and reduced-motion/mobile behavior.
- Added deterministic pytest coverage using temporary job roots and mocked media/network boundaries; no live media or user runtime data was accessed.

Executor commands and results:

- `python -m pip install --requirement requirements-dev.txt` — completed successfully with the accepted pinned packages.
- `python -m pytest -q` — final executor run completed with 28 tests passing in 0.52 seconds.
- `python -m py_compile app.py` — completed successfully.
- `node --check static/app.js` — completed successfully.
- Development import reported Socket.IO `threading` mode and non-production configuration.
- Production startup probes returned nonzero for missing and weak secrets and zero for a valid strong secret.
- `git diff --check` — completed with no whitespace errors (Git emitted Windows LF/CRLF conversion notices only).
- Product-surface search found no pandas, Eventlet, Flask-Session, or Toastify references.
- `git ls-remote --heads origin localUseOnly` returned no branch; `origin` and local `main` remain present.

Limitations for independent testing:

- No live network/media download was attempted by design.
- A real-browser visual smoke check was not run in the executor pass; template rendering and explicit accessibility/UI contract assertions are automated, and browser verification remains for the independent tester.

## 2026-07-17 - RESOURCE-ATOMICITY-002 executor evidence

- Preserved the independent FAIL for `SECURE-JOB-ISOLATION-001` and implemented only the accepted corrective lifecycle/resource batch.
- Added registry-authoritative job lifecycle transitions with a consistent registry-lock then job-lock order. Admission now requires the same accepting registry identity; cleanup atomically marks an idle job closing and removes it before filesystem deletion.
- Cleanup and CSV replacement refuse active/reserved jobs. A filesystem deletion failure reconciles any surviving allowlisted files/retained bytes, restores the same job as an accepting registry entry, and returns a clear retryable error; deletion is no longer silently ignored.
- Added configurable `MAX_ACTIVE_TASKS_PER_JOB`, `TASK_BYTE_RESERVATION`, and `MAX_JOB_BYTES`. A whole request reserves task and byte capacity before any background thread is created.
- Added per-index reservation tracking plus active, reserved-byte, and retained-byte accounting. Thread-start failures and worker completion/failure release exactly their reservation without underflow.
- Worker success measures the final tagged artifact, atomically checks cumulative retained bytes before allowlisting, and reconciles the reservation. Per-artifact or cumulative overflow is deleted and published as failure; partial outputs are removed after worker failure.
- README now documents the new defaults, whole-request refusal, conservative reservations, authoritative size reconciliation, and cleanup restoration behavior.

Executor commands and results:

- Focused lifecycle/resource selection — 6 tests completed successfully in 0.19 seconds; 28 deselected.
- First full `python -m pytest -q` — 34 tests completed successfully in 0.55 seconds.
- Second full `python -m pytest -q` — 34 tests completed successfully in 0.58 seconds.
- `python -m py_compile app.py` — completed successfully.
- `node --check static/app.js` — completed successfully; JavaScript was not modified in this batch.
- `python -m pip check` — `No broken requirements found.`
- `git diff --check` — no whitespace errors; only existing Windows LF/CRLF conversion notices.
- Post-check process inventory found no running `python.exe` or `pythonw.exe` process, so no test server or hung pytest process remained.

Independent tester handoff:

- Re-run the focused race/cap/rollback tests plus the full suite and compare frozen product hashes.
- Inspect registry/job lock ordering, close/restore transitions, partial-spawn behavior, and actual-byte overflow deletion.
- No live network/media operation or protected runtime data was accessed.

## 2026-07-17 - CAPACITY-SUPPLYCHAIN-003 executor evidence

- Preserved the historical `SECURE-JOB-ISOLATION-001` FAIL and `RESOURCE-ATOMICITY-002` PASS_WITH_RISKS while implementing only the accepted capacity, source-boundary, expiry, and dependency remediation batch.
- Added positive configuration enforcement for `MAX_SOURCE_BYTES`, `MAX_JOBS`, `MAX_TOTAL_JOB_BYTES`, and `JOB_TTL_SECONDS` with documented defaults of 100 MB, 100 jobs, 2 GB, and 3,600 seconds.
- Added yt-dlp `max_filesize` plus progress-hook aborts when a known total, estimated total, or downloaded byte count is greater than the source cap. Equality remains allowed; worker failure cleanup removes every confined `output_base.*` artifact and releases reservations.
- Added atomic registry-wide job-slot and retained-plus-reserved byte accounting. Job and global capacity are checked under the registry lock before job-directory or background-thread creation, while actual artifact reconciliation replaces reserved bytes without underflow or drift.
- Added deterministic HTML/JSON HTTP 503 capacity responses. Full capacity with no eligible expired job creates no job directory.
- Added an injectable monotonic activity clock and opportunistic request-time TTL reaping. Only expired accepting idle jobs are claimed; active, reserved, closing, and path-invalid jobs are skipped.
- Expired jobs remain registered and consume slot/byte capacity while closing. Filesystem deletion occurs outside locks; failure reconciles surviving allowlisted files, restores and touches the same accepting job, and preserves authoritative accounting.
- Updated `python-dotenv` from `1.1.1` to `1.2.2`; the updated pinned requirements installed successfully and the dependency vulnerability audit found no known vulnerabilities.
- README now documents source, job, global-byte, and TTL defaults; whole-request refusal; deterministic 503 behavior; expiry safety; cleanup/reconciliation; and the one-worker process-local constraint.

Executor commands and results:

- Focused capacity/source/TTL selection — 17 tests completed successfully in 0.25 seconds; 36 deselected.
- First final-state full `python -m pytest -q` — 53 tests completed successfully in 0.84 seconds.
- Second final-state full `python -m pytest -q` — 53 tests completed successfully in 0.78 seconds.
- `python -m pip install --requirement requirements.txt` — installed `python-dotenv==1.2.2`; all other accepted pins were already satisfied.
- `python -m py_compile app.py` — completed successfully.
- `node --check static/app.js` — completed successfully; frontend files were not modified in this batch.
- `python -m pip check` — `No broken requirements found.`
- `python -m pip_audit -r requirements.txt` — `No known vulnerabilities found.`
- `git diff --check` — no whitespace errors; only existing Windows LF/CRLF conversion notices.

Independent tester handoff:

- Re-run the source-hook equality/overflow, concurrent job/global-byte capacity, 503 rollback, fake-clock activity/TTL, outside-root protection, deletion-outside-lock, and restore/reconciliation tests.
- Compare the executor's frozen hashes for `app.py`, `tests/test_app.py`, `README.md`, and `requirements.txt` before and after testing.
- No live media/network operation, deployment credential, `.env` value, or protected user runtime data was accessed.

## 2026-07-18 - CAPACITY-SUPPLYCHAIN-003 manual-close corrective evidence

- Preserved the first independent `CAPACITY-SUPPLYCHAIN-003` tester verdict of FAIL. This corrective pass addresses only its deterministic manual cleanup/upload capacity-release defect.
- Changed `close_if_idle` to mark an idle job `closing` while keeping the same registry entry, slot, retained bytes, and reserved bytes capacity-bearing throughout filesystem deletion.
- Added registry-atomic `replace_closing`: after successful deletion it allocates a new opaque job directory while the old closing entry remains registered, inserts the new accepting entry, and removes the old entry under the registry-then-job lock order. Concurrent creation or admission cannot observe a free-capacity window.
- Added explicit closing finalization for TTL reaping so its prior capacity-held delete-outside-lock semantics remain unchanged.
- Manual cleanup and CSV upload now restore/reconcile the same closing job after deletion failure. Replacement-directory allocation failure also recreates/reconciles and restores the prior accepting job with a clear error.
- Hardened create/replacement allocation against opaque-ID registry collisions and directory-allocation rollback without changing dependency or UI scope.
- Added deterministic direct-registry and threaded route coverage with `MAX_JOBS=1` and `MAX_TOTAL_JOB_BYTES=5`: paused cleanup/upload deletion keeps exactly one job and five bytes, newcomer creation returns 503 with no extra directory, failure restores exact accounting, and success yields exactly one opaque replacement.

Corrective executor commands and results:

- Focused manual-close selection — 5 tests completed successfully in 0.15 seconds; 53 deselected.
- First final-state `python -m pytest -q` — 58 tests completed successfully in 0.76 seconds.
- Second final-state `python -m pytest -q` — 58 tests completed successfully in 0.85 seconds.
- `python -m py_compile app.py` and `node --check static/app.js` — completed successfully.
- `python -m pip check` — `No broken requirements found.`
- `python -m pip_audit -r requirements.txt` — `No known vulnerabilities found.`
- `git diff --check` — no whitespace errors; only existing Windows LF/CRLF conversion notices.

Independent tester handoff:

- Re-run the five focused closing-capacity tests and full suite against the frozen hashes below.
- Confirm paused manual deletion retains slot/bytes, replacement is one atomic registry transition, and failed deletion/allocation restores one coherent accepting job without exceeding either cap.
- No live media/network operation, `.env` value, credential, protected runtime data, UI, or unrelated workflow surface was accessed or modified.

## 2026-07-18 - CAPACITY-SUPPLYCHAIN-003 final independent verification

- Preserved the historical verdicts exactly: `SECURE-JOB-ISOLATION-001` `FAIL`; `RESOURCE-ATOMICITY-002` `PASS_WITH_RISKS`; initial `CAPACITY-SUPPLYCHAIN-003` `FAIL`.
- Final corrective verdict: `PASS_WITH_RISKS`.
- Focused manual-close race selection: 5 tests passed.
- Focused source/global/TTL selection: 19 tests passed.
- Full `python -m pytest -q`: 58 tests passed in 1.06 seconds; repeated full run: 58 tests passed in 0.82 seconds.
- `python -m py_compile app.py`, `node --check static/app.js`, `python -m pip check`, `python -m pip_audit -r requirements.txt`, and `git diff --check` passed.
- `python-dotenv==1.2.2` was confirmed and the point-in-time dependency audit reported no known vulnerabilities.
- The remote `localUseOnly` branch was absent. This does not prove deployment secret rotation, session invalidation, non-use, or reachable-history purge.
- Frozen product hashes were unchanged across independent testing. The tester left no live process or temporary residue and introduced no unexpected product worktree changes.
- Unverified by design: live yt-dlp/YouTube/iTunes, FFmpeg/media conversion, deployed production behavior, and a populated-browser end-to-end/visual flow.

## 2026-07-18 - CAPACITY-SUPPLYCHAIN-003 documentation QA closure

- Reconciled final tester evidence into `QA_REPORT.md`, `RISK_REGISTER.md`, `DEV_STATE.md`, `docs/PROJECT_STATE.md`, `docs/VERSION_LOG.md`, `docs/BOOTSTRAP_AUDIT.md`, and append-only shared workflow history.
- Marked the batch `COMPLETE_WITH_RISKS`; no new batch was started.
- Kept `RISK-001` open High for owner-controlled rotation/session/history actions and `RISK-012` open Medium for automatic source matching, rights, and provenance.
- Recorded residual one-worker process-local architecture, version-pinned-not-hash-pinned dependencies, point-in-time audit scope, and unverified live media/FFmpeg/deployment/populated-browser checks.
- Documentation QA did not modify product/source/test/dependency/UI files or `shared/locks.json`; post-reconciliation hashes were compared with the pre-reconciliation product hashes.

## 2026-07-18 - Current repository-description reconciliation

- Reconciled `docs/ARCHITECTURE.md`, `docs/REPO_PROFILE.md`, `docs/REPO_PROFILE.json`, `docs/REPO_MAP.md`, `docs/RUN_PROTOCOL.md`, `docs/TEST_STRATEGY.md`, `docs/DEPENDENCY_POLICY.md`, and `shared/context.md` to the final implementation and evidence.
- Current descriptions now record Flask-SocketIO threading/simple-websocket, standard-library in-memory CSV parsing, the one-worker process-local registry, pinned imageio-ffmpeg resolution, the 58-test pytest suite, capacity/source/TTL controls, and confirmed commands.
- Preserved bootstrap findings as historical entries in audit/version/history files.
- JSON parsing and documentation encoding/contradiction scans passed for the authorized surfaces. The out-of-scope `AGENTS.md` bootstrap command block still requires root reconciliation.
- Product/source/test/dependency/UI hashes remained identical to the pre-docs-QA baseline; `shared/locks.json` was not edited.

## 2026-08-14 - SELECT-ALL-QUEUE-004 executor evidence

- Raised default `SELECTION_LIMIT` from 20 to 2,000 so an imported CSV can be selected in one request.
- Select-all / master checkbox now select every imported track up to the configured limit. Copy no longer says “first 20”.
- `/download` uses `enqueue_indices`: a greedy reserved prefix starts immediately; the remainder is job-local pending without byte reservations. `/retry-failed` queues every failed track rather than slicing to 20.
- `process_song` drains pending after releasing a reservation. Tracks that cannot fit remaining retained bytes fail closed with a disk-budget error. Cleanup, replacement, and TTL treat pending as outstanding work.
- Direct `reserve_indices` callers keep all-or-nothing admission.

Executor commands and results:

- Focused pytest selection (`selection or pending or task_ceiling or full_imported or never_fitting or fake_clock_ttl or valid_upload or cumulative_budget or start_and_worker`): 16 passed, 46 deselected in 0.74s.
- `python -m pytest -q`: 62 passed in 1.64s.
- `python -m py_compile app.py`: completed successfully.
- `node --check static/app.js`: completed successfully.
- `python -m pip check`: No broken requirements found.
- `git diff --check`: completed with no whitespace errors.
- `python -m pip_audit -r requirements.txt`: unavailable in this environment (`No module named pip_audit`).

Frozen product hashes before independent TEST:

- `app.py` sha256 `974dd33e5fd7f5e5d0f267dea8f26eeab0456e0dc37a156f6b4e8bcc526bb547`
- `static/app.js` sha256 `e72e746403512a603a87fb3e9d06097129e5d0d6e26a67accb1cc1131d6feabd`
- `templates/index.html` sha256 `dd5c93d3c9d3f5e94d0fe4d6c13d5aa1e3a78b80bf4dda4dba4ff94760431aeb`
- `tests/test_app.py` sha256 `98ce2463c94fd8cf2790c0d55da229adb0fba2e8b59ea41bacdef52e9de51a34`
- `README.md` sha256 `42972ee46c94e732ea77047a7e6f0459c8e9b402480fa53692a54684daceb01d`

Limitations for independent testing:

- No live network/media download was attempted.
- A populated-browser visual smoke check was not run; template rendering and UI-contract assertions are automated.
- `pip-audit` was not installed in the executor environment.

## 2026-08-14 - SELECT-ALL-QUEUE-004 independent verification

- Frozen product hashes were unchanged after TEST.
- Focused queue selection: 13 passed, 49 deselected in 0.49s.
- Full `python -m pytest -q`: 62 passed in 1.49s; repeated: 62 passed in 1.36s.
- `python -m py_compile app.py`, `node --check static/app.js`, `python -m pip check`, and `git diff --check` passed.
- `python -m pip_audit -r requirements.txt` remained unavailable.

## 2026-08-14 - SELECT-ALL-QUEUE-004 documentation QA closure

- Reconciled QA, risk, project state, version history, architecture, run protocol, test strategy, and shared records with the independent `PASS_WITH_RISKS` verdict.
- Released cooperative locks. Historical FAIL/PASS_WITH_RISKS verdicts were not rewritten.
- Marked the batch `COMPLETE_WITH_RISKS`; no new batch was started.

## 2026-09-03 - PORTFOLIO-FINALIZATION-005 execution

- User accepted Option A: keep the same public SignalForge repository and valid
  history; remove current-tree internal artifacts; reconcile presentation,
  security, and evidence; add a synthetic visual; and prepare GitHub Support
  cleanup for the already-unreferenced sensitive object.
- Removed three tracked `_tmp_mine/*.txt` transcripts and two tracked
  `.cursor/hooks/state/*.json` files from the current tree. Added narrow ignore
  rules and publication-guard checks for both prefixes.
- Replaced the obsolete absolute workstation root in
  `docs/REPO_PROFILE.json` with a repository-relative root and added a
  publication check for absolute user-home paths in tracked text.
- Reconciled the canonical SignalForge identity, same-repository history policy,
  current 118-test/green-CI baseline, completed credential rotation/ref
  containment, and pending GitHub cached-object removal across active public and
  workflow documentation. Historical tester verdicts and dated 58/62-test
  evidence remain preserved.
- Verified the local application in a browser using a synthetic three-track CSV.
  The import rendered the job dashboard and queue, Select All worked, meaningful
  content was present, and no console warning/error or framework error overlay
  was detected. No live provider, FFmpeg, or media operation was invoked.
- The available browser could not export screenshot pixels. Instead of
  misrepresenting a fabricated screenshot, created
  `docs/assets/signalforge-interface.svg`, clearly labeled as an illustrated
  overview derived from the verified DOM. A local static render was visually
  inspected and contains only synthetic names and no workstation path, job ID,
  credential, personal data, or copyrighted media.
- Redacted all-reachable-history scanning reported zero high-confidence private
  key, GitHub, AWS, Slack, Stripe, or JWT token patterns. Broad numeric heuristics
  in the removed files produced non-secret log-number candidates; no value was
  printed. Prior Phase 1 content review found workstation paths and internal
  conversation/state, not an additional credential.

Frozen product/dependency hashes before TEST:

- `app.py`: `29d6afac6ec3a5353e85ffc0ddb3fb2208776d801116df4f8b53203d189cd968`
- `static/app.js`: `20a9590610e9490b1ebebdf8cccf8c19cba4dcd2162aba62a42b79db0c7b81c2`
- `templates/index.html`: `393f4443c0751268b1e6762a908a8a81fec351f19f9154a797527bdbc49bd066`
- `tests/test_app.py`: `2d49aa8f8777c197a1915566bca8132f4ac63b0410c3fd4c0eab5ae6029af3af`
- `requirements.txt`: `44f43a36b5289ec2ff94991716e33a884ed5521836a9a02ebbba2d9296d4ea3f`
- `requirements-dev.txt`: `86083a12fab36857cf6ac4f6946656408ebed0f1ae64e5f52bdf85175525ef6a`
- `Procfile`: `d3381efb2d38acb788ec7ef10a98af915a72ea0a38b1ba86d87c1871a3f28b4d`
- `.python-version`: `48d0992617133b1e48ec7bbb2b7582a859e50bf1ec472b38611cf0cfee5d3fa5`

## 2026-09-03 - PORTFOLIO-FINALIZATION-005 initial independent TEST

- Verdict: `FAIL`. All 118 tests, syntax checks, dependency consistency,
  publication guard, SVG XML parsing, protected hashes, staged diff hygiene,
  removed-path/ignore checks, and merged-branch ancestry checks passed.
- The new execution section had been inserted inside the 2026-07-18
  documentation-QA section, causing three historical bullets to be attributed
  to the 2026-09-03 entry and violating append-only log semantics.
- Returned to EXECUTE for a bounded documentation-only ordering repair. The
  failed verdict remains preserved and a fresh independent TEST is required.

## 2026-09-03 - PORTFOLIO-FINALIZATION-005 corrective independent TEST

- Verdict: `PASS_WITH_RISKS` on frozen staged tree
  `58fda0eec08d661d6ccb1d217e1639a9f902083a`.
- `python -m pytest -q`: 118 passed in 5.46s.
- Python/JavaScript syntax, `pip check`, publication guard, staged diff, SVG
  XML, all eight protected hashes, removed-path/ignore checks, and all seven
  merged remote branch ancestry checks passed.
- The staged tree and patch hashes were identical before and after TEST; no
  repository side effect occurred. Product/runtime/template/test/dependency
  content remained byte-identical.
- The historical 2026-07-18 bullets are restored to their section, the 2026-09-03
  entries are append-only, and the initial `FAIL` remains preserved.

## 2026-09-03 - PORTFOLIO-FINALIZATION-005 documentation QA closure

- Reconciled the corrective verdict, initial failure, acceptance evidence,
  browser/visual limitations, security state, risks, project state, version
  history, and shared records.
- Closure recommendation: `COMPLETE_WITH_RISKS`. Public CI/fresh-clone and
  GitHub metadata/merged-branch corroboration follow the normal commit; failure
  in those checks reopens the batch.
- Released the cooperative repository lock. Product sources remained frozen.
