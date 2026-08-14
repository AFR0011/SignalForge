# Dependency Policy

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## Dependency authorities

- Production Python packages: `requirements.txt`.
- Development/test packages: `requirements-dev.txt`, which includes production requirements and pins pytest.
- Python runtime: `.python-version`.
- Install/build behavior: `build.sh`.
- Production process topology: `Procfile`.
- FFmpeg selection: `FFMPEG_PATH` validation in `app.py` or the executable supplied by pinned `imageio-ffmpeg`.
- YouTube JS runtime: host `deno` (default) or `node` via `YTDLP_JS_RUNTIME` / `YTDLP_JS_RUNTIME_PATH`. `build.sh` does not install it; Render and other production hosts must supply the executable.
- Browser Socket.IO client: vendored `static/socket.io.min.js` (socket.io-client 4.8.1 from `https://cdn.socket.io/4.8.1/socket.io.min.js`, SHA-256 `b0e735814f8dcfecd6cdb8a7ce95a297a7e1e5f2727a29e6f5901801d52fa0c5`).

## Current policy

- Direct Python requirements use exact release pins. The verified set includes `yt-dlp[default]==2026.7.4`, `imageio-ffmpeg==0.6.0`, and remediated `python-dotenv==1.2.2`.
- `build.sh` performs only `python -m pip install --requirement requirements.txt`; it does not download or extract an external FFmpeg archive or a JavaScript runtime.
- The production server is Gunicorn with exactly one `gthread` worker and four threads; Eventlet is not a dependency.
- New or updated packages require compatibility review, license/provenance review, `pip check`, focused/full tests, and a point-in-time vulnerability audit.
- New external binaries require a trusted origin and checksum/signature or equivalent verifiable artifact provenance.

## Locking and reproducibility

- Exact direct-version pins reduce mutable-reference risk.
- No transitive lockfile or `--require-hashes` manifest exists. Exact versions alone do not prove the identity of index artifacts or fully freeze transitive resolution.
- `imageio-ffmpeg` is version pinned, but the resolved packaged executable must still be smoke-tested and its binary provenance reviewed for release.
- The audited `pip-audit` result is point-in-time evidence and must not be treated as a permanent guarantee.

## Update procedure

1. Review release notes, supported Python/platform versions, licenses, and security advisories.
2. Update the exact pin and install in a disposable environment using the appropriate requirements file.
3. Run focused compatibility tests, the 58-test full suite, Python/JavaScript syntax, and `pip check`.
4. Run `python -m pip_audit -r requirements.txt` and record date/result/limitations.
5. For yt-dlp, Requests, Socket.IO/simple-websocket, Gunicorn, or imageio-ffmpeg changes, run a controlled one-worker live integration smoke test with legally permitted media before release.
6. Freeze/compare product and dependency-authority hashes through independent verification.

## Supply-chain improvements still required

- Generate reviewed transitive lock metadata with hashes and install using hash enforcement where deployment tooling permits.
- Automate recurring dependency audits in CI and define a supported runtime/platform matrix.
- Establish binary provenance/checksum evidence for the packaged or overridden FFmpeg executable.
- Provide a checksum-pinned Deno (or Node) install on production hosts such as Render; the application fails closed without a JS runtime, and `build.sh` does not vendor one.
- Document emergency update/rollback ownership for yt-dlp and other rapidly changing external-service adapters.

## Current evidence

- `python-dotenv==1.2.2` is present; vulnerable 1.1.1 is absent.
- Independent `python -m pip check` passed.
- Independent point-in-time `python -m pip_audit -r requirements.txt` reported no known vulnerability.
- Full 58-test suite passed twice with mocked network/media boundaries.
- Live package installation provenance, target deployment, yt-dlp service compatibility, and FFmpeg execution remain release-owner checks.
