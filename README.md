# Signal Forge / SpotifyDownAutomater

Signal Forge is a small Flask and Socket.IO workspace that turns a CSV track list into an isolated download queue. Each browser session owns one opaque job ID. Completed files live in that job's confined directory and are available only through server-authorized URLs.

> Use this application only for media you are legally permitted to download. Search results are selected automatically and may not be the intended recording. You are responsible for reviewing source terms and copyright rules in your jurisdiction.

## Runtime model

Jobs, ownership records, progress, rate limits, and concurrency controls are held in memory. **Production must use exactly one worker.** Multiple workers would have independent registries and would break job ownership/progress. The committed `Procfile` uses one Gunicorn `gthread` worker with four threads.

Job files are stored below `DATA_ROOT` in a random per-job directory. Uploaded CSV bytes are parsed in memory and are not written to disk. Files remain until the user clears the inactive job or the host removes ephemeral storage; there is no guaranteed retention period. Do not upload sensitive listening data to a deployment you do not trust.

## Setup

Python 3.14.6 is declared in `.python-version`.

```bash
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install --requirement requirements-dev.txt
```

Create a strong secret for any persistent or production deployment:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Set it as `SECRET_KEY` without committing it. Development may omit the value, in which case the app logs a warning and generates a new ephemeral key on every process start. Production fails to start when the key is missing, shorter than 32 characters, or an obvious placeholder.

## Configuration

| Variable | Purpose | Default |
|---|---|---|
| `SECRET_KEY` | Signs the opaque job cookie and per-job CSRF tokens | Ephemeral in development; required in production |
| `APP_ENV=production` | Enables production secret and secure-cookie checks | Development |
| `DATA_ROOT` | Parent directory for isolated job folders | OS temp directory + `spotifydownautomater` |
| `FFMPEG_PATH` | Optional absolute/relative executable override | Executable supplied by pinned `imageio-ffmpeg` |
| `PORT` | Direct development server port | `5000` |

Application limits may be changed through Flask configuration when embedding/testing. Defaults are a 2 MB request, 1 MB CSV, 2,000 rows, 500 characters per consumed field, 20 selections per request, two concurrent media operations, eight queued-or-active tasks per job (`MAX_ACTIVE_TASKS_PER_JOB`), a 100 MB source-download cap (`MAX_SOURCE_BYTES`), 100 MB per final artifact (`MAX_ARTIFACT_BYTES`), a 100 MB conservative reservation per admitted task (`TASK_BYTE_RESERVATION`), a 500 MB cumulative retained-artifact budget per job (`MAX_JOB_BYTES`), 100 process-local jobs (`MAX_JOBS`), a 2 GB process-wide retained-plus-reserved budget (`MAX_TOTAL_JOB_BYTES`), one-hour idle expiry (`JOB_TTL_SECONDS=3600`), 250 MB total ZIP input, and 5 MB artwork. All capacity and TTL settings must be positive.

Task, job-slot, and byte capacity is reserved atomically before a directory or background thread is created. A request that would exceed a per-job or process-wide ceiling is rejected as a whole. Manual cleanup and CSV replacement keep the old closing job registered—with its slot and retained bytes—through filesystem deletion, then atomically swap in the new opaque job and directory. There is no intermediate free-capacity window. When no expired idle job can be reclaimed, new sessions receive a clear HTTP 503 response and no job directory is created. yt-dlp is given the source cap and aborts when a known total, estimate, or downloaded byte count exceeds it; exactly the configured limit is allowed. After download/tagging, the reservation is reconciled against authoritative file size. Oversized artifacts, source-limit aborts, failed thread starts, and worker failures release reservations and remove confined partial outputs.

Idle accepting jobs are opportunistically reaped after one hour of process-local monotonic time. Queued, active, reserved, closing, and path-invalid jobs are never reaped. Filesystem deletion occurs outside registry/job locks while the closing job continues to consume its capacity slot and bytes. If deletion fails, surviving allowlisted files and retained bytes are reconciled and the same job is restored and touched for a later retry.

## CSV format

Files must be UTF-8 with unique headers. `Song` and `Artist` are required. `Album` and `Genres` are optional; other columns are ignored.

```csv
Song,Artist,Album,Genres
Midnight Drive,Nova Lines,Afterglow,"Electronic, Synthwave"
Paper Moons,The Low Signals,,Indie
```

Blank required fields, malformed quoting, excessive rows/bytes/field lengths, and extra values without headers are rejected before a job is created.

## Commands

Development (local only):

```bash
python app.py
```

Production, matching the `Procfile`:

```bash
gunicorn --worker-class gthread --workers 1 --threads 4 --bind 0.0.0.0:${PORT:-5000} app:app
```

Build environments should run only:

```bash
python -m pip install --requirement requirements.txt
```

FFmpeg is resolved from a validated executable `FFMPEG_PATH` or from `imageio-ffmpeg`; the build script does not download unchecked archives.

## Tests

Tests use temporary job roots and mock all network/media operations. They never download live media.

```bash
python -m pytest -q
python -m py_compile app.py
node --check static/app.js
```

## Security and privacy notes

- The signed cookie contains only the current opaque job ID; song data and file paths never enter it.
- Every mutating HTTP route requires a per-job CSRF token.
- File, ZIP, Socket.IO room, and cleanup access require ownership of the current job.
- Filenames are deterministic server-generated names and paths must remain directly below the job directory.
- Cleanup is POST-only and atomically closes admission before removing an idle job. It refuses queued, active, or reserved work; a filesystem deletion failure restores the same job to an accepting, retryable lifecycle instead of silently losing registry state.
- Cover-art responses are checked for status, content type, HTTPS, and byte size.
- This is not an account system or durable/private cloud store. Deploy behind appropriate network and platform controls.
- Job counts, byte budgets, activity clocks, expiry, and rate limits are process-local; the one-worker production constraint is required for them to remain authoritative.
