# Publication Readiness

SignalForge is the canonical public repository for this project. It keeps its
existing name and authentic valid commit history. The portfolio presentation
focuses on the backend and reliability work actually present: isolated jobs,
bounded concurrency, atomic capacity accounting, path confinement, CSRF
protection, session-scoped ownership, real-time progress, and failure recovery.

## Current publication status

- [x] Public under the neutral SignalForge identity.
- [x] Current GitHub Actions workflow passes its publication, dependency, syntax,
  and 118-test verification contract.
- [x] Current tree contains no committed media/ZIP artifacts or usable `.env`
  secret.
- [x] README and security policy state the legal-use, source-identity,
  non-affiliation, one-worker, and process-local boundaries.
- [x] Internal transcript dumps and editor-generated state are removed from the
  current tree and blocked from recommit.
- [x] Public presentation uses an interface overview built only from synthetic
  track data and verified local DOM content.
- [ ] GitHub Support confirms removal of the already-unreferenced historical
  sensitive object and cached direct-SHA views.
- [ ] Controlled live provider/FFmpeg, deployed one-worker, and populated-browser
  accessibility verification is completed if a public deployment is ever
  proposed.

## History and security decision

A historical branch once tracked `.env` with a session/CSRF signing credential.
The owner confirmed that the credential was rotated and removed from active use.
The affected commit is absent from advertised branches and tags and from fresh
clones, but GitHub has continued to serve the unreferenced object through a known
direct address.

Valid `main` history will not be rewritten for this incident. Rewriting it would
change legitimate commit identities without removing an object that is already
outside advertised history. The remaining action is a GitHub Support request for
cached-view/reference removal and server-side garbage collection. The request
must identify the repository, deleted commit and historical `.env` path, confirm
rotation/invalidation and ref removal, and must not include the credential value.

Three development transcript files and two editor-state files were also removed
from the current tree. Their non-secret historical versions remain part of the
preserved development record; current-tree deletion is not described as
historical erasure.

## Claims that are supported

SignalForge can truthfully be described as a Flask and Socket.IO asynchronous
media-processing workspace with:

- opaque session-scoped jobs;
- ownership-scoped status and artifact routes;
- CSRF-protected mutations;
- bounded per-job and service-wide resource admission;
- thread-safe lifecycle and capacity accounting;
- failure recovery and cleanup semantics;
- job-scoped real-time progress;
- deterministic path-confined artifacts;
- extensive pytest coverage with mocked network/media operations;
- an explicitly documented single-worker production constraint.

At the 2026-09-03 publication baseline, 118 local tests pass and public `main`
CI is green. These automated results do not substitute for live provider,
browser, FFmpeg, deployment, load, restart, or retention verification.

## Claims to avoid

Do not describe SignalForge as:

- a commercial, hosted, or managed media service;
- an official integration with Spotify, YouTube, Apple, or another platform;
- a DRM bypass system;
- proof that arbitrary third-party media can legally be downloaded;
- a horizontally scalable multi-worker service;
- durable private storage or account-level multi-tenant authentication;
- independently verified against live media providers or a production deployment.

## Portfolio framing

Recommended short description:

> Backend-focused Flask and Socket.IO application for isolated asynchronous media jobs, with bounded resource admission, session-scoped authorization, real-time progress, failure recovery, and automated security/reliability tests.

The provider-facing behavior is secondary to the engineering case study: safely
coordinating untrusted uploads, external I/O, concurrent work, temporary
artifacts, and cleanup under explicit resource ceilings.

## Visual and privacy policy

Visuals and demos must use synthetic track data and must not contain browser
tokens, real listening history, private filenames, workstation paths, credentials,
or copyrighted audio/artwork. Runtime CSVs, generated media, ZIP files, job
directories, transcript dumps, and editor state are never publication inputs.

## License

Repository code remains under the Apache License 2.0 in `LICENSE`. That license
does not grant rights to third-party media or provider services.
