# QA Report

Workflow schema: `agentic-workflow/v2`
Project: SignalForge
Repository profile: software
Initialized: 2026-07-17

## Current cycle

- Batch: `PORTFOLIO-FINALIZATION-005`
- Initial tester verdict: `FAIL`
- Corrective tester verdict: `PASS_WITH_RISKS`
- Closure recommendation: `COMPLETE_WITH_RISKS`
- Corrective frozen tree:
  `58fda0eec08d661d6ccb1d217e1639a9f902083a`
- Evidence date: 2026-09-03

The presentation/privacy batch satisfies its locally testable acceptance criteria.
It removes current-tree transcript/editor state, prevents recurrence, preserves
product behavior and all valid history, makes the public narrative truthful, and
adds a synthetic-data interface overview. It does not close GitHub's cached
direct-object risk or verify live media, FFmpeg, deployment, full browser
accessibility/end-to-end behavior, multi-worker operation, or legal source
identity.

## Verdict history

- `SECURE-JOB-ISOLATION-001`: `FAIL`. Preserved historical lifecycle/resource
  failure.
- `RESOURCE-ATOMICITY-002`: `PASS_WITH_RISKS`.
- `CAPACITY-SUPPLYCHAIN-003` initial implementation: `FAIL`.
- `CAPACITY-SUPPLYCHAIN-003` corrective pass: `PASS_WITH_RISKS`.
- `SELECT-ALL-QUEUE-004`: `PASS_WITH_RISKS`.
- `PORTFOLIO-FINALIZATION-005` initial TEST: `FAIL` because the new execution
  record interrupted an older append-only log section.
- `PORTFOLIO-FINALIZATION-005` corrective TEST: `PASS_WITH_RISKS` after the
  log-order repair and a fresh complete verification pass.

No prior `FAIL` or `PASS_WITH_RISKS` verdict is superseded or rewritten.

## Corrective acceptance evidence

| Acceptance area | Independent evidence | Result |
| --- | --- | --- |
| Application regression | `python -m pytest -q`: 118 passed in 5.46s | Pass |
| Python/JavaScript syntax | `python -m compileall -q app.py tests tools`; `node --check static/app.js` | Pass |
| Installed dependency consistency | `python -m pip check`: no broken requirements | Pass |
| Publication policy | `python tools/publication_guard.py` | Pass |
| Patch hygiene | `git diff --cached --check` | Pass |
| Interface visual structure | SVG parsed as XML; synthetic labels and no-live-provider boundary inspected | Pass with pixel-level tester limitation |
| Protected sources | Eight SHA-256 hashes matched; protected staged diff empty | Pass |
| Internal artifacts | Removed-prefix tracked count zero; both ignore probes passed | Pass |
| Repository identity/history | No rewrite; 84 valid baseline commits preserved; seven feature tips are ancestors of `main` | Pass |
| Documentation integrity | Historical bullets restored; execution and initial FAIL appended after the prior final section | Pass |
| Tester isolation | Corrective staged tree and patch hashes identical before/after TEST; no repository side effect | Pass |

Root corroboration after the corrective TEST also passed the 118-test suite in
3.66s, syntax, dependency consistency, publication guard, JSON/SVG parsing,
protected hashes, ignore checks, current-tree workstation-path scan, and staged
diff check.

## Browser and visual evidence

A local development instance imported a three-row synthetic CSV. The browser
showed the job dashboard and queue, Select All updated the synthetic selection,
the page had meaningful content, and no console warning/error or framework error
overlay was detected. No source-provider, media, FFmpeg, or download operation
ran.

The in-app browser's pixel export was unavailable. The repository therefore
contains a clearly labeled SVG interface overview derived from the verified DOM,
not a claimed screenshot. Root rendered that SVG locally and visually confirmed
that it contains only synthetic track names and no workstation path, credential,
personal job identifier, real listening history, or copyrighted media.
Independent TEST verified its XML and text/content boundaries but could not
independently inspect pixels.

## Security and privacy evidence

- The owner confirmed the historical session/CSRF credential was rotated and
  removed from active use.
- The affected commit is absent from advertised refs and fresh clones.
- GitHub's known direct object view remains externally available pending Support
  cleanup; `RISK-001` remains High/open.
- Redacted reachable-history scanning reported zero high-confidence private-key,
  GitHub, AWS, Slack, Stripe, or JWT patterns and printed no secret values.
- The five removed files contained internal conversations, generated state, and
  workstation paths. A broad phone-number heuristic produced noisy numeric-log
  candidates; Phase 1 review did not identify another credential or regulated
  private record.
- Preserving valid history means non-secret historical transcript versions remain
  reachable. Current-tree deletion is not described as historical erasure.

## Residual risks and unavailable checks

- GitHub cached-view/reference removal and server-side garbage collection remain
  an external High risk until Support confirms the known URLs no longer resolve.
- Local `pip-audit` is unavailable. The committed CI workflow installs and runs
  pinned `pip-audit==2.10.1`; all audit evidence is point-in-time.
- Automatic source matching, rights, and provenance remain open.
- Live yt-dlp/YouTube/iTunes, artwork, FFmpeg, target deployment, load, restart,
  retention timing, full populated-browser accessibility/end-to-end behavior,
  and multi-worker coordination were not verified.
- Requirements are exact-version pinned but not hash pinned.
- Public-commit CI, final metadata, branch-ref cleanup, and fresh-clone
  corroboration are performed after the normal commit and recorded in the
  external Phase 2 report. A failure there reopens the batch.
