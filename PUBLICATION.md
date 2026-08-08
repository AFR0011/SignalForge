# Publication Readiness

Signal Forge is being prepared as a public engineering portfolio repository. The public presentation should emphasize the backend and reliability work that is actually present in the codebase: isolated jobs, bounded concurrency, atomic capacity accounting, path confinement, CSRF protection, per-session ownership, real-time progress, cleanup/recovery behavior, and testable failure handling.

## Before making the repository public

- [ ] Rename the GitHub repository from `SpotifyDownAutomater` to `signal-forge` (or another neutral Signal Forge name).
- [ ] Review Git history for old credentials, cookies, generated media, deployment secrets, or other material that should not become public. Current-tree checks cannot sanitize historical blobs.
- [ ] Confirm the repository contains no copyrighted media files, exported playlists that should remain private, or generated ZIP/download artifacts.
- [ ] Run the required GitHub Actions workflow successfully on the final publication branch.
- [ ] Confirm the public README still states the legal-use boundary and the lack of affiliation with media platforms.
- [ ] Confirm screenshots, if added, contain only synthetic/demo track data and no browser tokens, private filenames, or personal listening history.

## Claims that are supported

The repository can truthfully be described as a Flask/Socket.IO asynchronous media-processing workspace with:

- opaque per-session jobs;
- ownership-scoped status and artifact routes;
- CSRF-protected mutations;
- bounded per-job and service-wide resource admission;
- thread-safe job lifecycle/accounting;
- failure recovery and cleanup semantics;
- real-time progress over Socket.IO;
- deterministic path-confined artifacts;
- pytest coverage with mocked network/media operations;
- single-worker production constraints documented and enforced operationally.

## Claims to avoid

Do not describe Signal Forge as:

- a commercial or client product;
- an official Spotify, YouTube, Apple, or other media-platform integration;
- a DRM bypass system;
- a horizontally scalable multi-worker service;
- durable/private cloud storage;
- a system with account-level multi-tenant authentication;
- proof that arbitrary third-party media can legally be downloaded.

## Portfolio framing

Recommended short description:

> Backend-focused Flask and Socket.IO application for isolated asynchronous media jobs, with bounded resource admission, session-scoped authorization, real-time progress, failure recovery, and automated security/reliability tests.

The downloader/media-source behavior is an implementation detail. The engineering signal is the safety and coordination model around untrusted uploads, external I/O, concurrent work, temporary artifacts, and cleanup.

## License

The project remains under the Apache License 2.0 currently committed in `LICENSE`.
