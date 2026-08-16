# Library Write-Through

**Date:** 2026-08-16
**Status:** Draft for review

## Goal

On local development, move each finished MP3 into a durable library folder so a long queue (hundreds of tracks) is not stopped by the 500 MB per-job disk budget or the 250 MB ZIP cap. The job only holds in-flight work. The user does not harvest files via ZIP.

**Start selected** and **Retry failed** keep their current meaning. **Choose source** is unchanged in this batch.

## Out of scope

- Raising `MAX_JOB_BYTES`, `ZIP_MAX_BYTES`, or `TASK_BYTE_RESERVATION`
- Chunked or streaming ZIP
- A destination picker on every job
- Auto-triggering one browser download per completed track
- Expanding Choose source with excluded top hits or **Load more** (follow-up below)
- Object storage / Render-durable libraries
- Changing automatic YouTube ranking

## Current behavior

`process_song` writes the MP3 under the job directory inside `DATA_ROOT`, then `retain_artifact` adds its size to `job.retained_bytes` (cap 500 MB). Pending tracks fail with “This request exceeds the remaining per-job disk budget” once `retained_bytes + TASK_BYTE_RESERVATION` would exceed that cap. ZIP sums completed job files and rejects above 250 MB. **Clear job** deletes the job directory. Per-row **Download** and **Download ZIP** are how the user takes files home.

`create_app` hardcodes those byte ceilings; they are not read from `.env`.

## Design

### 1. When write-through is on

Write-through is **on** when the app is not in production (`_production_requested` is false).

Write-through is **off** on Render / `APP_ENV=production` / `FLASK_ENV=production`. Production keeps today’s job-dir retain, per-row **Download**, and **Download ZIP**.

### 2. Library root

Default library root is `<home>/Music/SignalForge`, created with mode `0o700` on first successful save (Windows: `%USERPROFILE%\Music\SignalForge`).

The overview panel always shows that destination (short label `Music\SignalForge`, full path in helper text). **Change folder** is hidden until the default root cannot be created or is not writable.

On that failure:

- **Start selected** is disabled.
- An error sits next to the destination control, not only in a toast.
- The user supplies a fallback directory (path field; a native folder picker is allowed as progressive enhancement).
- `POST /library-root` (CSRF, same `20 per minute` limiter as `/download`) accepts `{ "path": str }`, creates the directory if needed, and rejects anything that cannot be created writable. 400 malformed, 409 unusable, 200 `{ "library_root": "<absolute>" }`. Production returns 409. The path is not written to `.env`.
- After success, that directory is the process-wide library root for the rest of this `python app.py` run.

Library writes must resolve inside that root. Reject `..`, extra segments, and any path whose parent is not the library root.

### 3. Filename

Use the CSV song title after existing `format_title` (Title Case, feat. parentheses stripped, `'(s)` / `'(t)` preserved). Do not put the artist in the filename; artist remains in MP3 tags.

Strip characters Windows does not allow in names (`\ / : * ? " < > |`) and control characters. Collapse whitespace. Trim trailing dots and spaces. Cap the stem at 96 characters. If the stem is empty, use `Track`.

First file: `Halo.mp3`. If that path exists and is a non-empty file, use `Halo (2).mp3`, then `Halo (3).mp3`, and so on. Never replace a non-empty library file. Replace only a zero-byte leftover at the chosen name.

Allocate the name under a process lock so two in-flight tracks cannot take the same suffix.

### 4. Download path

Unchanged until the MP3 is tagged in the job directory:

1. Search/rank or forced watch URL, size caps, JS runtime, `noplaylist`, tagging, artwork.
2. If write-through is off: `retain_artifact` as today.
3. If write-through is on: allocate a library name, `os.replace` (or copy+unlink if cross-device) into the library root, then release the job reservation **without** adding the file to `job.files` / `retained_bytes`.
4. Publish `success` with message `Saved` and the library filename. Do not set `download_url`.

A track whose status is `success` (Saved) is not queued again by **Start selected** or **Retry failed**.

### 5. Move failure

If tagging succeeded but the library write fails:

- Leave the MP3 in the job directory.
- Do not count it as Saved. Row is `failed` with a write error; show per-row **Download**.
- Surface the same error on the destination control.
- **Retry failed** for that index retries the **move** when the job still has the file. It does not search YouTube again unless the job file is gone.

Choose source still applies only when automatic YouTube download failed and leftovers exist.

### 6. UI

- Metric **Ready** becomes **Saved** (count of `success` rows). Overall progress is saved / selected.
- **Start selected** remains the only primary action. Disable it when write-through is on and the library root is unusable.
- Hide **Download ZIP** while write-through is on. Show it in production.
- Per-row **Download** only when the artifact is still in the job.
- **Clear job** still confirms. It deletes only the job directory, never the library folder.
- Existing `aria-live` toast region: toast on start, destination failure, and job finished — not on every Saved row. Row text carries per-track status.
- Status color is never the only signal; keep the status text.

Do not virtualize the 250-row table in this batch.

### 7. Isolation and cleanup

`DATA_ROOT` remains the only tree for in-flight job files. Library files are user data outside `DATA_ROOT` and are not reaped by TTL or cleanup.

CSRF, job ownership, admission (`MAX_ACTIVE_TASKS_PER_JOB`, reservations, pending queue), and in-attempt 403 fallback stay unchanged. Reservations still use `TASK_BYTE_RESERVATION`; they return to the pool when a track Saves or fails, so a long queue is limited by concurrency, not by accumulated retained bytes.

## Testing

Mock yt-dlp and HTTP. Point the library root at a temp directory. Do not hit live YouTube. Do not write under the developer’s real Music folder in tests.

- Local success: file is `Halo.mp3` (Title Case, no artist in the name); `job.files` / `retained_bytes` do not include it; status is Saved; no `download_url`.
- Collision: a second saved track with the same formatted title becomes `Halo (2).mp3`; the first file is unchanged.
- Empty leftover at `Halo.mp3` is replaced; a non-empty `Halo.mp3` is not.
- Unwritable default root: Start is rejected until `POST /library-root` sets a writable fallback; error is on the destination control. Production POST returns 409.
- Move failure: artifact stays in the job; retry moves it without `extract_info` / search.
- Saved indices are omitted from a later **Start selected** / **Retry failed** payload handling (same as today’s `success` skip).
- Production config: write-through does not run; `retain_artifact` and ZIP behavior still apply.
- Existing choose-source, admission, ZIP, and Socket.IO contract tests still pass.

## Intended files

- `app.py` — library root, filename allocation, move after tag, success/fail payloads, production gate, `POST /library-root`
- `templates/index.html` — Saved metric, destination copy, ZIP hidden when write-through is on
- `static/app.js` — Saved progress, disable Start when destination is unusable, hide ZIP, row Saved vs Download
- `static/style.css` — destination helper only if existing tokens are not enough
- `tests/test_app.py` — cases above
- `README.md` — one sentence that local runs save into Music/SignalForge
- `.env.example` — optional comment that the library path is not configured there (default Music/SignalForge)

## Rollback

Revert the files above. MP3s already in the user’s library folder are left in place.

## Follow-up (not this batch)

Choose source today shows at most three leftover hits after movie/clean/variant/duration/tried-id filters.

A later batch may:

- Include up to three of the top search hits that ranking excluded, and/or
- Add **Load more** to page further leftover or excluded hits from the **same** `extract_flat` search (no second search, no pasted URLs, still stored-id allow-list and same-origin thumbs).
