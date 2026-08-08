# Publication Readiness

Signal Forge is being prepared as a public engineering portfolio repository. The public presentation should emphasize the backend and reliability work that is actually present in the codebase: isolated jobs, bounded concurrency, atomic capacity accounting, path confinement, CSRF protection, per-session ownership, real-time progress, cleanup/recovery behavior, and testable failure handling.

## Before public portfolio publication

- [x] Run the required GitHub Actions workflow successfully on the publication branch.
- [x] Confirm the current tree contains no committed MP3/audio/ZIP artifacts through the publication guard.
- [x] Confirm the public README states the legal-use boundary and lack of affiliation with media platforms.
- [ ] Publish under the neutral `Signal Forge` / `signal-forge` repository identity rather than the legacy `SpotifyDownAutomater` name.
- [ ] Use a clean modern Git history for the public portfolio repository, or deliberately rewrite the legacy history before changing this repository's visibility.
- [ ] Confirm screenshots, if added, contain only synthetic/demo track data and no browser tokens, private filenames, or personal listening history.

## Legacy history finding

A review of representative historical commits did not surface a real API key, password, private cookie, or deployment credential. It did surface obsolete 2024-era automation experiments that are no longer part of the current application, including Selenium/`undetected_chromedriver`/`selenium_stealth` code targeting `spotifydown.com`, comments about Cloudflare detection, and example Spotify track URLs.

Those experiments are historical development context, not part of the modern Signal Forge architecture. They are also poor portfolio signal and unnecessarily complicate the public project's legal/security story. The preferred publication path is therefore:

1. keep this legacy repository private as the development archive;
2. merge or otherwise preserve the modern publication-ready tree here;
3. create the public `signal-forge` repository from the cleaned modern tree with a fresh initial history;
4. retain the Apache-2.0 license, security policy, CI, tests, and publication boundaries in the public repository.

A fresh public history is not intended to misrepresent authorship or conceal the origin of the project. It simply publishes the maintained application rather than every abandoned experiment that preceded it.

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
