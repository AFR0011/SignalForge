# Choose Source 30-Second Preview

**Date:** 2026-08-18
**Status:** Draft for review

## Goal

On a failed track’s Choose source dialog, let the user play a ~30-second preview of the audio that would be downloaded from a leftover YouTube hit, without saving that track or embedding YouTube.

Automatic download stays the default. **Start selected**, **Retry failed**, **Use this source**, and **Load more** keep their current meaning. **Choose source** stays failure-only.

## Out of scope

- Pasting a Spotify or YouTube URL (follow-up)
- YouTube player embeds or widening CSP `img-src` / `frame-src` to YouTube
- Prefetching clips when the dialog opens
- Writing previews into `Music/SignalForge` or counting them as Saved
- Changing leftover filters, ranking, or `PICKER_SOURCE_LIMIT`
- Raising job/ZIP byte caps
- Populated-browser / live-YouTube verification (RISK-013)

## Current behavior

Choose source cards show a same-origin thumbnail, title, channel, duration, and **Use this source**. Thumbnails are `GET /tracks/<index>/source-thumbs/<id>` for stored leftover ids only. CSP is `default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws: wss:`. There is no `media-src` and no audio in the dialog.

A full download of a leftover still goes through `process_song` / `download_song_from_youtube` with the current player clients, JS runtime, size cap, `noplaylist`, and `match_filter`.

## Design

### 1. Preview route

**GET `/tracks/<index>/source-previews/<video_id>`**

- Same session job and ownership as thumbnail GET. Limiter: `60 per minute` (same class as thumbs).
- 200 `audio/mpeg` when the index is failed and `video_id` is an 11-character id already in `source_choices[index]`.
- 404 for a missing job, non-failed index, unknown/forged id, or a clip that cannot be built (403, match-filter skip, oversize, FFmpeg/trim failure).
- Same no-job status as thumbnail GET (`404`).

The handler does not accept a pasted URL. It builds `https://www.youtube.com/watch?v=<id>` only after the stored-id check.

CSP: add `media-src 'self'` only. Do not add YouTube hosts.

### 2. Clip production

On a cache miss, using the existing JS runtime, FFmpeg resolver, `MAX_SOURCE_BYTES`, `noplaylist`, `match_filter`, and YouTube player_client extractor args:

1. Download that watch URL into the **job directory**, not the library root.
2. Limit the media to **30 seconds** from the start (yt-dlp download section/range or an FFmpeg trim). The result must not be a full-length track.
3. Reject the attempt if the output exceeds `PREVIEW_MAX_BYTES` (**5_000_000**).
4. Produce an MP3. Do not tag as a library save. Do not call `save_mp3_to_library` or `retain_artifact`. Do not add the path to `job.files`. Do not set `download_url`. Do not mark the row success or queued.

Cache key: `preview-<video_id>.mp3` under the job directory. A later GET for the same id on the same job returns that file. Job replace, clear, and TTL delete it with the rest of the job directory.

One clip build in flight **per job**. A second GET waits on that job’s preview lock, then returns the cached file or 404. Do not start stacked yt-dlp processes.

A failed build does not change `source_choices`, `can_choose_source`, or row status. **Use this source** still queues a real download.

### 3. Dialog

Each leftover card (including those revealed by **Load more**) gets a **Play** control, `type="button"`.

- First click sets the shared dialog `<audio>` (or `Audio`) `src` to `/tracks/<index>/source-previews/<id>` with `credentials: "same-origin"`, shows “Loading preview…”, then plays.
- While that card is playing, the control reads **Pause**. Click pauses.
- Play on another card pauses the first and starts the second.
- Closing the dialog (Close, Escape, or backdrop) pauses and clears the audio `src`.
- No autoplay when the dialog opens.
- Preview 404: that card shows “Preview unavailable”, Play disables, **Use this source** stays enabled. Other cards are unchanged.

Do not mark the row queued on Play. Do not POST `/choose-source` for a preview.

### 4. Error handling

| Case | Result |
|---|---|
| Forged or unbound `video_id` | 404; Play shows preview unavailable |
| Track not failed / job missing | 404 (same as thumbnail GET) |
| YouTube 403 or match-filter skip on the clip | 404; row stays failed; leftovers unchanged |
| Clip larger than 5 MB | 404 |
| Second Play while a clip is building | Wait on the job lock, then 200 from cache or 404 |
| Library folder unusable | Preview still allowed (this batch does not 409 Choose source) |

### 5. Testing

Mock yt-dlp and HTTP. Do not hit live YouTube.

- GET preview for a stored leftover id returns bounded MP3 bytes after a mocked 30s clip; `job.files` does not gain that path; library root is untouched.
- Forged id → 404. Non-failed index → 404.
- Mocked download 403 → 404; `can_choose_source` stays true.
- Two overlapping preview GETs on one job do not start two mocked downloads.
- Cached second GET does not call yt-dlp again.
- HTML/JS contract: **Play** is `type="button"`; `media-src 'self'` is in CSP; `app.js` uses `/source-previews/`.
- Existing choose-source CSRF, Load more, and thumbnail tests still pass.

## Intended files

- `app.py` — preview route, 30s clip helper, `PREVIEW_MAX_BYTES`, CSP `media-src`, per-job preview lock/cache
- `templates/index.html` — optional shared `<audio>` node if easier than constructing it in JS
- `static/app.js` — Play/Pause, one player, loading and unavailable states
- `static/style.css` — Play control only if existing button tokens are not enough
- `tests/test_app.py` — cases above

## Rollback

Revert the files above. Cached preview MP3s die with the job directory.

## Follow-up (not this batch)

Paste a Spotify or YouTube link when leftovers are the wrong recordings.
