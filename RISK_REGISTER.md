# Risk Register

Workflow schema: `agentic-workflow/v2`
Project: SignalForge
Repository profile: software
Initialized: 2026-07-17

## Current summary

The original thirteen risks remain traceable below. Status changes are based on implementation plus independent automated evidence; they do not erase the original findings. `SELECT-ALL-QUEUE-004` closes `COMPLETE_WITH_RISKS`.

- One High external security risk remains open: GitHub cached/direct-object
  removal for an already-unreferenced historical credential. The credential
  itself is rotated and inactive.
- One Medium product/legal risk remains open: automatic source matching, rights, and provenance.
- Supply-chain, deployment, privacy-retention, capacity, and verification mitigations retain explicit residual limitations.
- Current-tree transcript/editor-state exposure is mitigated in
  `PORTFOLIO-FINALIZATION-005`; non-secret historical versions remain visible
  by the accepted history-preservation decision.

## Risks

### RISK-001 - Historically exposed session/CSRF secret

- Severity: High; Category: security; Status: Open / externally contained,
  server-side cleanup pending.
- Original evidence: Remote branch `localUseOnly` tracked `.env`; reachable commit `0dce90c` added it. Variable-name-only inspection found `SECRET_KEY`; its value was not read or displayed.
- Current evidence: The owner confirmed rotation and removal from active use.
  Independent verification found the `localUseOnly` branch absent, no
  advertised branch/tag contains the commit, and a fresh clone does not contain
  the object. Rotation invalidates sessions signed by the old Flask secret.
  Production configuration tests also prove missing, weak, and placeholder
  secrets fail closed.
- Unresolved: GitHub still serves the already-unreferenced commit/object through
  its known direct address. This is not reachable from valid `main` history and
  cannot be removed by rewriting `main`.
- Required action: Request GitHub Support cached-view/reference removal and
  server-side garbage collection; verify the known direct commit/blob URLs no
  longer resolve before closing this risk. Never retrieve, publish, or reuse the
  exposed value.

### RISK-002 - Cross-user state and file disclosure

- Original severity: High; Category: privacy/security; Status: Mitigated in the supported one-worker topology.
- Evidence: Opaque per-job IDs, isolated job directories/state, ownership checks on status/file/ZIP/cleanup, and per-job Socket.IO rooms are covered by cross-session access and room tests in the 58-test suite, which passed twice.
- Residual: Ownership records are process-local; multi-worker deployment is unsupported and tracked under RISK-007/RISK-009.

### RISK-003 - Public destructive cleanup

- Original severity: High; Category: data loss; Status: Mitigated.
- Evidence: Cleanup is POST-only, requires per-job CSRF and ownership, refuses active/reserved jobs and outside-root paths, and restores coherent state on deletion/allocation failure. The five focused corrective race tests passed and the full 58-test suite passed twice.
- Historical note: The `SECURE-JOB-ISOLATION-001` FAIL and the initial `CAPACITY-SUPPLYCHAIN-003` FAIL remain preserved; this status reflects the later corrective implementation only.

### RISK-004 - Background worker loses request session

- Original severity: High; Category: correctness; Status: Mitigated.
- Evidence: Background tasks receive copied immutable job/song values and do not read request-local session state. Automated worker/session and room-targeting coverage passed in the repeated full suite.

### RISK-005 - Valid CSV result page crashes

- Original severity: High; Category: correctness; Status: Mitigated.
- Evidence: Valid-upload rendering and UI-contract tests pass; the complete 58-test suite passed twice.

### RISK-006 - Upload path traversal/overwrite

- Original severity: High; Category: security; Status: Mitigated.
- Evidence: CSV bytes are bounded and parsed in memory; client filenames are not used as storage paths. Job directories and artifact paths use generated identities plus containment checks. Upload, traversal, ownership, and outside-root tests pass in the repeated suite.

### RISK-007 - Unbounded resource consumption

- Original severity: High; Category: availability; Status: Mitigated with residual Medium architecture/operations risk.
- Evidence: Server-side request/CSV/row/field/selection/rate/task/artifact/job/ZIP/source/global-byte/job-count limits are enforced. Atomic admission, conservative reservations, source abort cleanup, TTL reaping, manual-close accounting, and failure reconciliation are covered by the focused 5-test and 19-test selections plus two full 58-test runs.
- Residual: Capacity, rate, TTL, and pending-queue state is process-local and requires exactly one production worker. Pending tracks do not reserve bytes until admitted; never-fit retained-byte cases fail closed. Cross-job process-budget stalls may not drain until this job completes other work or receives another queue request. No live load, long-duration, multi-process, or deployed capacity test was run.
- Required action: Keep the one-worker deployment constraint or replace process-local authority with shared durable coordination before scaling horizontally; run controlled deployment/load verification.

### RISK-008 - Non-reproducible, unverified supply chain

- Original severity: High; Category: provenance; Status: Mitigated with residual Medium supply-chain risk.
- Evidence: Python packages, including `yt-dlp==2026.7.4`, `imageio-ffmpeg==0.6.0`, and `python-dotenv==1.2.2`, are exact-version pinned. The build no longer downloads an unchecked moving FFmpeg archive. `pip check` and the independent point-in-time `pip-audit` passed with no known vulnerability reported.
- Residual: Requirements are version pinned, not hash pinned; no lock/hash manifest or artifact-signature verification exists. A point-in-time audit cannot cover later disclosures or index artifact substitution. Live FFmpeg resolution/execution was not verified.
- Required action: Generate reviewed hashes/lock metadata, verify binary provenance, automate recurring audits, and run a controlled FFmpeg smoke test.

### RISK-009 - Runtime/deployment incompatibility

- Original severity: High; Category: compatibility; Status: Mitigated with residual Medium deployment risk.
- Evidence: The obsolete Eventlet production worker was replaced with one Gunicorn `gthread` worker; the build is now platform-neutral dependency installation; a Python runtime file exists; syntax, imports through the test suite, and dependency consistency passed in the audited environment.
- Residual: No live Render/production deployment, production credential path, external media call, or packaged FFmpeg execution was verified. The one-worker requirement is architectural.
- Required action: Deployment owner must validate the declared runtime, strong rotated secret, one-worker command, writable ephemeral storage, yt-dlp/FFmpeg execution, and shutdown/restart behavior in the target environment.

### RISK-010 - File identity races and broken links

- Original severity: Medium; Category: correctness; Status: Mitigated.
- Evidence: Jobs and file identities are server-generated, admission/replacement is atomic, the server returns authoritative allowlisted URLs, and collision/path/access tests pass in the repeated full suite.

### RISK-011 - Retained private listening data

- Original severity: Medium; Category: privacy; Status: Mitigated with residual Medium retention risk.
- Evidence: Uploaded CSV bytes are parsed in memory and are not persisted. Per-job storage is isolated; user cleanup and fake-clock-testable opportunistic idle TTL reaping are implemented and documented. TTL/reconciliation tests are included in the focused 19-test pass.
- Residual: Reaping is request-time and process-local, so deletion is not a guaranteed wall-clock schedule; completed media and metadata remain until cleanup/reaping/host removal. No deployed retention behavior was observed.
- Required action: Confirm an owner-approved retention/privacy policy and deployment cleanup behavior; use scheduled durable expiry if guaranteed deletion is required.

### RISK-012 - Wrong/unverified media and artwork

- Severity: Medium; Category: correctness/provenance/legal; Status: Open.
- Evidence: Source and artwork selection remain automatic. Size/response boundaries reduce resource risk but do not establish recording identity, licensing, or provenance. README warns that automatic results may be wrong and requires lawful use.
- Required action: Add preview/selection or match-confidence review, record source provenance, validate external responses, and obtain product/legal policy confirmation before public deployment.

### RISK-013 - No automated verification

- Original severity: Medium; Category: verification; Status: Mitigated with residual Medium release-process risk.
- Evidence: The deterministic suite has grown to 118 tests. Current public
  GitHub Actions installs Python 3.14.6, runs the publication guard and
  `pip-audit`, checks Python/JavaScript syntax, and runs pytest. The
  `SELECT-ALL-QUEUE-004` historical tester evidence remains 13 focused and
  62 full tests twice; the 2026-09-03 finalization preflight passes all 118.
- Residual: No populated-browser end-to-end/accessibility run, live
  media/FFmpeg integration, deployed smoke test, or supported-runtime matrix was
  independently verified. The local browser DOM/render check is not a live-media
  or deployment result.
- Required action: Maintain CI, add a supported-runtime matrix if the support
  promise expands, run a populated-browser accessibility smoke test, and perform
  controlled live/deployment checks only with legally permitted media.

### RISK-014 - Published internal transcripts and editor state

- Original severity: Medium; Category: privacy/professional hygiene; Status:
  Mitigated in the current tree with accepted historical residual.
- Original evidence: Three tracked `_tmp_mine/*.txt` transcript dumps and two
  `.cursor/hooks/state/*.json` files exposed internal conversations,
  workstation paths, and generated identifiers.
- Current evidence: `PORTFOLIO-FINALIZATION-005` removes all five from the
  current tree, adds narrow ignore rules, and makes the publication guard reject
  either tracked prefix. The obsolete absolute path in
  `docs/REPO_PROFILE.json` is replaced with `.`.
- Residual: Non-secret versions remain reachable in preserved valid history.
  Current-tree deletion is not historical erasure.
- Required action: Keep the guard active. If a future redacted scan identifies a
  real credential or regulated/private data in preserved history, stop and
  reconsider a narrowly scoped rewrite.

### RISK-015 - Public presentation contradicted repository reality

- Original severity: Medium; Category: correctness/professional presentation;
  Status: Mitigated pending public publication checks.
- Original evidence: `PUBLICATION.md` described a private legacy repository
  and fresh successor although this same repository was public; active
  governance used the legacy product name and 58/62-test baselines; GitHub
  description was vague and topics were empty.
- Current evidence: The finalization batch establishes SignalForge as the
  canonical same-name, history-preserved repository; separates historical
  evidence from the current 118-test/CI baseline; removes internal current-tree
  artifacts; and adds a synthetic-data interface overview.
- Residual: GitHub description/topics and fresh-public-clone verification occur
  after the normal publication commit.
- Required action: Verify public metadata, CI, merged-branch cleanup, and fresh
  clone before closing the batch.
