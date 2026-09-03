# Security Policy

Signal Forge is a personal/research software project that demonstrates isolated asynchronous job processing, resource controls, and secure file delivery. It is not a managed media service and is not affiliated with any streaming, video, or music platform.

## Supported use

The application is intended for local development, private demonstration, and controlled deployment. Do not expose it directly to the public Internet without an independent deployment review, reverse-proxy/TLS configuration, monitoring, and validation of the host's storage and process limits.

Use the application only for media you are legally permitted to download and process. Source-provider terms and copyright rules remain the user's responsibility.

## Secrets

Persistent and production deployments must set a strong `SECRET_KEY` of at least 32 characters. Keep secrets in environment configuration and never commit them to the repository.

Do not commit:

- `.env` files or deployment credentials;
- private cookies, browser exports, API tokens, or source-provider credentials;
- generated media, ZIP archives, or job directories;
- logs containing user-supplied track lists or operational details that should remain private.

The committed `.env.example` contains no usable secret.

### Historical credential incident

A deleted historical branch once tracked `.env` with a session/CSRF signing
credential. The owner confirmed that the credential was rotated and removed
from active use. The affected commit is absent from advertised refs and fresh
clones. GitHub cached direct-object removal remains pending with GitHub Support,
so this incident is not marked fully closed.

Valid `main` history is intentionally preserved because the sensitive commit
is already unreferenced; rewriting current history would not remove GitHub's
server-side cached object. Never retrieve, publish, or reuse the old value.

## Application security model

The current application uses:

- an opaque server-generated job identifier stored in the signed Flask session cookie;
- per-job CSRF tokens for mutating routes;
- ownership checks for job status, file delivery, ZIP creation, cleanup, and Socket.IO room membership;
- deterministic server-generated filenames plus path-confinement checks;
- request, CSV, selection, source, artifact, per-job, and process-wide capacity limits;
- bounded background concurrency;
- rate limiting;
- secure cookies in production;
- restrictive browser security headers;
- single-worker deployment so process-local ownership and capacity accounting remain authoritative.

The browser session is the ownership boundary. Signal Forge does not provide user accounts, durable authentication, multi-tenant authorization, or persistent private storage.

## Process and storage boundary

Job state, rate-limit state, progress, reservations, and retained-byte accounting are process-local. Production must run exactly one application worker unless the registry and coordination model are replaced with shared durable infrastructure.

Completed files are temporary job artifacts, not durable storage. Process restarts can discard in-memory job state, and ephemeral hosting can remove files independently.

## Dependency security

Runtime dependencies are directly version-pinned in `requirements.txt`; development dependencies are pinned in `requirements-dev.txt`. CI installs the declared environment and runs `pip-audit` before the test suite.

Dependency updates should be followed by the complete CI verification flow.

## Reporting

If you find a security issue, report it privately to the repository owner. Do not open a public issue containing credentials, exploit payloads, private media data, or instructions that would expose another user's job artifacts.
