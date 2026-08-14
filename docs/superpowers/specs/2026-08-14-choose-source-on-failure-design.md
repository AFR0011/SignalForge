# Choose Source On Failure

**Date:** 2026-08-14
**Status:** Draft for review

## Goal

When automatic YouTube download fails (no approved source, or every approved source 403s), let the user pick one of up to three remaining search hits for that track and download it through the existing job.

Automatic download stays the default. **Start selected** and **Retry failed** do not change meaning. The picker is failure-only.

## Out of scope

- Picker before first download, on low-confidence matches, or on a successful track
- YouTube player embeds or pasted watch URLs
- Widening CSP `img-src` to `i.ytimg.com`
- Changing automatic ranking beyond what this picker needs
- Populated-browser / live-YouTube verification (RISK-013)
- Rights or provenance guarantees (RISK-012 remains open)

## Current behavior

`process_song` calls `download_song_from_youtube`, which searches, ranks, and retries approved watch URLs. On failure it publishes `failed` with “Download failed. You can retry this track.” The file cell goes empty. **Retry failed** re-runs the same automatic path.

CSP is `img-src 'self' data:`. Job state is process-local memory. Mutations require the current job plus CSRF.

## Design

### 1. Trigger and dialog

**Choose source** appears only on a row whose status is `failed` and whose stored picker list is non-empty. It lives in the file cell beside the hidden download link.

Clicking it opens one shared page dialog for that track:

- Heading: song title and artist
- Up to three cards: same-origin thumbnail, title, channel, duration (`m:ss` when duration is known)
- Per card: **Use this source**
- **Close**; Escape closes; a background click may close the dialog but does not start a download
- No YouTube embed

Fewer than three usable hits → fewer cards. Zero usable hits → button disabled and the fail message is “Download failed. No alternate sources found.”

While the index is queued, pending, or downloading, the button is ignored and **Use this source** is rejected.

### 2. Candidate storage

On automatic failure, the worker writes a job-local list for that index from the search that just ran. It does not search again when the dialog opens.

Build the list as follows:

1. Start from the `extract_flat` search entries of that attempt.
2. Drop entries without a valid 11-character YouTube id (`[A-Za-z0-9_-]{11}`).
3. Drop ids already tried in that automatic attempt (downloaded, 403, or match-filter skip).
4. Drop duration `< 90` or `>= 600` when duration is present.
5. Drop movie/scene titles (existing `_MOVIE_TITLE`).
6. Drop clean/non-explicit and processed-variant titles (existing `_CLEAN_TITLE` / `_VARIANT_TITLE`). Music videos, lyric videos, visualizers, label channels, and soundtrack channels stay eligible.
7. Rank remaining by `view_count` descending, then original search order.
8. Keep at most three records: `id`, `title`, `channel`, `duration` (`null` if missing).

Store them on the `Job` in memory only (`source_choices: dict[int, list[dict]]`). Do not write them under `DATA_ROOT`. Clear the list when the track succeeds, when a new automatic attempt starts for that index, when a chosen id 403s (remove that id only), and when the job is replaced, cleared, or reaped.

### 3. Routes

All routes use the current session job, the same ownership rules as `/download`, and the same `20 per minute` limiter as `/download` for POST `/choose-source`. Source-list and thumbnail GETs use the existing `60 per minute` file/index style.

**GET `/tracks/<index>/sources`**

- 200 `{ "sources": [ { "id", "title", "channel", "duration" } ] }` when the index is failed.
- Thumbnail URLs are not stored; the client builds `/tracks/<index>/source-thumbs/<id>`.
- 409 if the index is not failed or is out of range.
- 403 if the job is missing.

**POST `/choose-source`**

- CSRF required, JSON `{ "index": int, "video_id": str }`.
- 409 if the track is not failed, is already reserved/queued/pending, or `video_id` is not in that index’s stored list.
- 400 if CSRF is missing/invalid or the payload is malformed.
- On success, queue that single index through `queue_indices` / the existing reservation and pending path. Record a one-shot forced id on the job so `process_song` downloads `https://www.youtube.com/watch?v=<id>` and does not search or rank.
- Response 202 `{ "job_id", "started" }` like `/download`.

**GET `/tracks/<index>/source-thumbs/<video_id>`**

- 200 JPEG only when `video_id` is in that index’s stored list.
- Fetch only `https://i.ytimg.com/vi/<video_id>/hqdefault.jpg` (no redirects to other hosts, timeout, byte cap at or below artwork limits).
- Do not persist the image. On fetch failure or oversize: 404.
- Unknown or unbound id: 404.

Fail Socket.IO payloads include `can_choose_source` (boolean) and keep a human `message`. Persist that flag on `job.statuses[index]` so a full page refresh can render the button. `setTrackState` shows **Choose source** from the flag. Opening the dialog GETs `/tracks/<index>/sources` for the cards. Extra payload keys must not break existing row updates.

### 4. Download path

`download_song_from_youtube` gains an optional `watch_url`. When set, skip search/ranking and download that URL with the existing size cap, JS runtime, player clients, and `match_filter`. Visual sources remain downloadable (filter still rejects clean/variant/movie/duration).

If the chosen URL 403s: track stays failed, that id is removed from `source_choices[index]`, remaining entries stay, and `can_choose_source` reflects what is left.

**Retry failed** still means automatic search for every failed index. A new automatic attempt replaces that index’s stored list.

### 5. UI details

- One dialog node in `templates/index.html`, wired in `static/app.js`, styled in `static/style.css`.
- Focus moves into the dialog; restore focus to **Choose source** on close.
- **Use this source** disables the cards, closes the dialog, and drives queued → downloading → success on that row.
- Thumbnail error → hide the image; title, channel, and duration still render.
- Successful download hides **Choose source** and shows the existing file link.

### 6. Error handling

| Case | Result |
|---|---|
| Unknown, expired, or already-removed `video_id` | 409; row stays failed |
| Track not failed; job/CSRF missing | Existing 409 / 403 / 400 |
| Admission full | Same pending-queue path as a one-track retry |
| Thumbnail fetch fails | Card without image |
| Chosen source 403s | Failed; id dropped; button remains if any cards left |
| Empty picker list | Disabled button; “No alternate sources found.” |

Isolation, byte caps, CSRF, and cleanup stay unchanged.

## Testing

Mock yt-dlp and HTTP. Do not hit live YouTube.

- Auto-fail stores at most three picker entries from raw search: label/lyric/soundtrack hits may appear; sub-90s, ≥10 minute, movie/scene, clean, and variant titles may not; tried ids may not.
- Fail payload sets `can_choose_source` correctly; empty list uses the no-alternates message.
- GET sources returns the stored list only for a failed index on the owned job.
- POST choose-source with a stored id queues a download that uses that watch URL and does not search. Forged id → 409. CSRF/ownership match `/download`.
- Thumbnail GET for a stored id returns bounded stubbed bytes. Unknown id → 404. The handler does not fetch an arbitrary URL.
- Chosen-id 403 leaves the track failed, drops that id, and keeps remaining entries.
- Retry-failed runs automatic search and replaces the stored list. Existing in-attempt 403 fallback among approved auto candidates remains covered.

## Intended files

- `app.py`
- `templates/index.html`
- `static/app.js`
- `static/style.css`
- `tests/test_app.py`
- `README.md` (one sentence on failed-track source choice)

## Rollback

Revert the files above. No migration. Picker state is memory-only.
