# Architecture

Workflow schema: `agentic-workflow/v2`
Project: SpotifyDownAutomater
Repository profile: software
Initialized: 2026-07-17

## System boundaries

- A browser uploads CSV bytes and controls one opaque job through Flask HTTP routes and Flask-SocketIO events.
- One application process owns the in-memory job registry, ownership records, rate limits, capacity accounting, activity clocks, and TTL decisions.
- Per-job files are confined below configurable `DATA_ROOT`; uploaded CSV bytes are parsed in memory and are not persisted.
- External adapters call yt-dlp/YouTube for media (requiring a host JavaScript runtime such as Deno), iTunes Search/artwork through Requests, FFmpeg through a validated override or pinned `imageio-ffmpeg`, and Mutagen for tags.

## Components and ownership

- `app.py`: configuration validation, standard-library CSV parsing, job registry/lifecycle, routes, Socket.IO rooms, capacity/TTL controls, media adapters, tagging, ZIP streaming, and cleanup.
- `templates/`: server-rendered upload/results workspace and allowlisted download list.
- `static/app.js`: selection, CSRF-protected actions, owned Socket.IO progress, downloads, and browser interactions.
- `static/socket.io.min.js`: vendored Socket.IO 4.8.1 client loaded same-origin under CSP `script-src 'self'`.
- `static/style.css`: responsive visual presentation.
- `requirements.txt`, `requirements-dev.txt`, `build.sh`, `.python-version`, and `Procfile`: dependency, runtime, test, build, and deployment authorities.
- `tests/`: deterministic pytest coverage with temporary job roots and mocked network/media boundaries.

## Data and control flow

1. A request obtains an opaque job ID stored alone in the signed cookie. Production requires a strong configured `SECRET_KEY`.
2. `/upload` validates CSRF, request/CSV/row/field limits, parses with `csv.DictReader`, and atomically replaces an idle job while retaining capacity through deletion.
3. `/download` or `/retry-failed` validates owned indices, reserves a greedy prefix against per-job task/byte and process-global byte ceilings, pending-queues the remainder without reservations, and starts background work only for reserved tracks.
4. A background task receives copied job/song data, joins process-wide concurrency control, resolves a host JS runtime, runs yt-dlp with a source-byte cap, resolves FFmpeg, tags the bounded artifact, and reconciles its reservation against actual bytes.
5. Progress is emitted only to the owned `job:<opaque-id>` room. Status, individual files, ZIP, and cleanup require current-job ownership; mutations require per-job CSRF.
6. Request-time fake-clock-testable TTL reaping claims only expired accepting idle jobs. Closing jobs retain slot/byte capacity during deletion; failure restores reconciled state.

## External interfaces

- HTTP: `GET /`, `POST /upload`, `POST /download`, `POST /retry-failed`, `GET /api/jobs/<job_id>`, `GET /jobs/<job_id>/files/<filename>`, `POST /download_zip`, and `POST /cleanup`.
- Socket.IO: client event `join_job`; server events `joined_job`, `join_error`, and owned `download_progress` messages.
- External systems: yt-dlp/YouTube plus a host JS runtime (Deno by default), iTunes Search/artwork, FFmpeg, and a Gunicorn-compatible deployment.

## Runtime and concurrency decisions

- Flask-SocketIO uses `threading` mode with `simple-websocket` support.
- Production is exactly one Gunicorn `gthread` worker with four threads. Multiple workers would create independent registries and violate ownership/capacity/progress authority.
- Registry/job multi-lock operations use registry-then-job ordering. Filesystem deletion runs outside locks while the closing registry entry remains capacity-bearing.
- Limits include request/CSV/selection/concurrency, a job-local pending queue, source/artifact/job/global bytes, job count, ZIP/artwork, rate, and idle TTL controls.

## Known debt and boundaries

- Process-local authority prevents horizontal multi-worker scaling without shared durable coordination.
- Requirements are version pinned but not hash pinned; dependency audit evidence is point-in-time.
- Automatic source selection does not establish recording identity, rights, or provenance.
- Live media/FFmpeg, deployed production, load/long-duration, and populated-browser flows remain unverified.
- Production hosts such as Render must supply Deno (or Node) on PATH or `YTDLP_JS_RUNTIME_PATH`; the build does not vendor a JS runtime.
