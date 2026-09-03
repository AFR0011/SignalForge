# Blueprint

Workflow schema: `agentic-workflow/v2`
Project: SignalForge
Repository profile: software
Initialized: 2026-07-17

## Product objective

Present SignalForge as an honest backend reliability case study while preserving
its application behavior, repository identity, and valid development history.

## Active batch

Status: CLOSED — `PASS_WITH_RISKS`
Batch ID: `PORTFOLIO-FINALIZATION-005`

Previous completed batch: `SELECT-ALL-QUEUE-004` (`PASS_WITH_RISKS`).

Completed batch: `PORTFOLIO-FINALIZATION-005` (`PASS_WITH_RISKS` after an
initial preserved `FAIL` and corrective retest).

### Objective

Remove current-tree internal artifacts, prevent their recurrence, reconcile
public documentation and metadata with verified reality, add a privacy-safe
synthetic interface visual, and publish through a normal descendant commit without
changing product/runtime behavior or rewriting valid history.

### Facts

- Public `main` is `5ef0258ef7c8b77224597a4ef33585d47e4794f8`
  with 84 commits and a successful GitHub Actions run.
- The local baseline passes 118 tests, Python/JavaScript syntax checks,
  `pip check`, and `tools/publication_guard.py`.
- Three `_tmp_mine/*.txt` transcripts and two
  `.cursor/hooks/state/*.json` files are tracked.
- `docs/REPO_PROFILE.json` contains an obsolete absolute workstation path.
- Active governance records still use the legacy project name and August 2026
  58/62-test baselines; historical results remain valid as dated evidence.
- The historical secret was rotated and removed from active use. Its commit is
  absent from advertised refs and fresh clones but remains served by GitHub via
  a known direct object address.
- Seven remote feature branches are fully merged into `main`.

### Assumptions

- Preserving commit history means accepting that deleted non-secret transcript
  versions remain in old valid commits; current-tree deletion is not described
  as historical erasure.
- The visual will use only synthetic data and may document the local application
  without claiming live-provider or deployed-service verification. The local
  browser's pixel-export facility was unavailable, so the visual is a clearly
  labeled interface overview derived from the verified DOM, not a screenshot.
- GitHub Support, not a `main` rewrite, owns removal of the already-unreferenced
  cached sensitive object.

### Unknowns

- GitHub Support response time and whether server-side cached-object removal will
  require additional private evidence.
- Live provider, FFmpeg, deployed one-worker, and populated end-to-end behavior
  remain outside this batch.

### Intended files

- `.gitignore`
- `tools/publication_guard.py`
- `README.md`
- `PUBLICATION.md`
- `SECURITY.md`
- `docs/assets/signalforge-interface.svg`
- `docs/REPO_PROFILE.json`
- the five tracked files being removed under `_tmp_mine/` and
  `.cursor/hooks/state/`
- `DEV_LOG.md` for append-only implementation evidence

### Allowed-adjacent files

- Workflow and active documentation surfaces updated during PLAN/QA/CLOSE:
  `AGENTS.md`, `BLUEPRINT.md`, `DEV_STATE.md`, `QA_REPORT.md`,
  `RISK_REGISTER.md`, `docs/REPO_PROFILE.md`, `docs/REPO_MAP.md`,
  `docs/PROJECT_STATE.md`, `docs/RUN_PROTOCOL.md`,
  `docs/TEST_STRATEGY.md`, `docs/DEPENDENCY_POLICY.md`,
  `docs/VERSION_LOG.md`, and `shared/*`.
- GitHub repository description, topics, and seven already-merged remote branch
  refs after local commit/test evidence is accepted.

### Out of scope

- Product code, tests, templates, dependencies, runtime configuration, media
  behavior, architecture refactoring, deployment, or public service hosting.
- History filtering, force-pushing, squashing, repository rename, successor
  creation, archival, or deletion of any commit reachable from `main`.
- Closing the legal/source-provenance risk or claiming live-provider,
  accessibility, deployment, multi-worker, or durable-storage verification.
- Retrieving, displaying, or including the historical secret value.

### Preconditions

- User accepted Option A, steps 3.1-3.16, on 2026-09-03.
- `shared/locks.json` has no conflicting owner.
- Independent read-only risk review found no Critical blocker and recommended
  `PROCEED_WITH_CONTROLS`.
- Product-source hashes are recorded before execution.

### Acceptance criteria

- Same public repository/name and every existing valid commit are preserved; the
  final publication is a normal descendant commit.
- Product code, tests, templates, dependencies, and runtime behavior are
  byte-for-byte unchanged.
- `_tmp_mine/**` and `.cursor/hooks/state/**` are absent from the current
  tree, ignored, and rejected by the publication guard.
- No current tracked file contains an absolute user-home/workstation path.
- Current public documentation uses the SignalForge identity, reports the
  118-test/current-CI evidence separately from historical 58/62-test runs, and
  records rotation/ref containment while keeping GitHub object removal open.
- Legal-use, source-identity, one-worker, process-local, and unverified-live-flow
  limitations remain prominent.
- The interface visual contains only synthetic data and no credentials, private
  filenames, listening history, or copyrighted media.
- Local focused/full checks and public CI pass; a fresh public clone reproduces
  the clean current tree and required checks.
- GitHub description/topics are accurate and only already-merged branch refs are
  removed.
- The Support request is prepared without the secret value and requires
  action-time confirmation before submission.

### Verification

- Preserve and re-check SHA-256 hashes for `app.py`, `static/app.js`,
  `templates/index.html`, `tests/test_app.py`, requirements, `Procfile`,
  and `.python-version`.
- `python -m pytest -q`
- `python -m compileall -q app.py tests tools`
- `node --check static/app.js`
- `python -m pip check`
- `python tools/publication_guard.py`
- `git diff --check`
- redacted current-tree and all-reachable-history secret scans without printing
  values; local `pip-audit` is recorded unavailable while CI runs it.
- inspect the interface visual and actual diff; obtain an independent tester
  verdict.
- wait for GitHub CI and repeat narrow verification from a fresh public clone.

### Protected inputs

- All valid commits and authorship/topology; product source/tests/templates;
  dependency/runtime declarations; `.env`, credentials, user media/CSV data,
  paths outside this repository, and all prior tester verdict history.

### Risks

- Historical transcript versions remain reachable because the user selected
  authentic-history preservation. A redacted scan finding a real credential or
  regulated/private data requires `STOP_NEEDS_HUMAN`.
- The direct-SHA GitHub object remains externally open until Support confirms
  removal; this batch cannot close it.
- Automatic matching/rights and unverified live/deployment behavior remain open.

### Rollback

- Before push, revert only this batch's working-tree changes.
- After a normal push, publish a normal revert commit if needed; never rewrite
  valid history.
- Deleted merged branch refs can be recreated at their recorded immutable tips.
- GitHub metadata can be restored from the recorded baseline.

### Evidence required for done

- File inventory and protected hashes, redacted privacy/secret checks, rendered
  visual inspection, full verification output, independent tester verdict,
  reviewed diff, normal commit/push proof, green public CI, fresh-clone evidence,
  final branch/metadata state, and explicit residual-risk records.
