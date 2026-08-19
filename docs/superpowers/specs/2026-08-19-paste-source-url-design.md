# Paste Spotify or YouTube Source URL

**Date:** 2026-08-19
**Status:** Draft for review

## Goal

When automatic YouTube download fails, let the user paste a Spotify track URL or a YouTube video URL in the Choose source dialog. Spotify paste becomes a new leftover list. YouTube paste becomes one previewable card. They still pick with Play and Use this source.

Automatic download stays the default. **Start selected**, **Retry failed**, **Use this source**, **Load more**, and **Play** keep their current meaning. **Choose source** stays failure-only.

## Out of scope

- YouTube player embeds or widening CSP `img-src` / `frame-src` / `media-src` beyond what preview already set
- Spotify album, playlist, artist, episode, or show URLs
- YouTube playlist, channel, or user URLs
- A Spotify API key or downloading audio from Spotify
- Changing leftover filters, ranking, `PICKER_SOURCE_LIMIT` (9), or `PICKER_PAGE_SIZE` (3)
- Raising job/ZIP byte caps
- Prefetching previews
- Pasting a URL on a successful track or before the first download
- Populated-browser / live-YouTube / live-Spotify verification (RISK-013)

## Current behavior

**Choose source** shows only when the row is `failed` and `can_choose_source` is true. That flag is true only when `source_choices[index]` is non-empty. Empty leftovers use “Download failed. No alternate sources found.” and hide the button. Library-folder failures hide it as well.

POST `/choose-source` accepts `{ index, video_id }` only if that 11-character id is already stored. GET `/tracks/<index>/sources` already returns `{ "sources": [] }` for a failed index with no cards. Play and thumbs allow only stored ids. `download_song_from_youtube(..., watch_url=...)` still applies `match_filter`. Preview builds also apply `match_filter` and need the bundled FFmpeg ContextVar.

There is no paste field and no Spotify URL handling.

## Design

### 1. Visibility

On every failed **download** (no matching source, 403, extract error, chosen-source 403, empty leftovers), set `can_choose_source` to **true** even if `source_choices[index]` is empty. Fail message is always:

`Download failed. You can retry this track or choose a source.`

Library-folder failures (`LibraryWriteError` / keep-outputs path) still set `can_choose_source` false and keep the library-folder message. The file already exists.

After a pasted or leftover id 403s: drop that id from the list; **Choose source** stays available (paste still works). `can_choose_source` stays true.

**Retry failed** still means automatic search. A new automatic attempt **replaces** that index’s stored list, including any pasted card.

### 2. Dialog

Keep the existing dialog. Above the cards, add:

- A text input, placeholder `Paste a Spotify or YouTube link`
- **Add link**, `type="button"`, quiet style like Load more

Empty leftover list: heading, paste field, and **Add link** still show. Cards area is empty until a YouTube card is added or a Spotify search fills it. Load more stays hidden until more than three stored hits exist.

**Add link** POSTs `/paste-source`. While it runs, disable the field, Add link, Load more, and card buttons (same busy pattern as Use this source). On success, replace the dialog’s stored list from the response, reset to the first page of three, and clear the input. On error, leave the current cards; announce the server message (429 uses the existing too-many-requests copy).

Clear the input when the dialog closes (Close, Escape, backdrop) so the next track does not inherit a half-typed URL.

Play, Pause, Use this source, thumbs, and 30-second previews are unchanged except that a pasted YouTube id is in the allow-list and skips match-filter (section 4).

No YouTube embed. CSP unchanged.

### 3. POST `/paste-source`

CSRF required. Same session job and ownership as `/choose-source`. Limiter: `20 per minute`. JSON `{ "index": int, "url": str }`.

- 202 is not used. This route does not queue a download.
- 200 `{ "sources": [ ... ] }` is the full updated `source_choices[index]` (0–9 cards), same shape as GET `/tracks/<index>/sources`, plus `"pasted": true` on cards that came from a YouTube paste.
- 409 if the track is not failed, is reserved/queued/pending, or the Spotify/YouTube lookup cannot proceed as in the error table.
- 400 if CSRF is missing/invalid, JSON is malformed, `index` is invalid, `url` is missing/too long (cap **500** characters), or the URL is not a Spotify track / YouTube video.
- 403 if the job is missing (same as other mutations).
- 429 when the limiter fires.

Parse `url` only as a string. Do not follow user-supplied redirects. Reject anything that is not:

**YouTube video:** `youtube.com/watch?v=`, `youtube.com/embed/`, `youtube.com/shorts/`, `youtube.com/live/`, `music.youtube.com/watch?v=`, `youtu.be/`. Extract the 11-character id (`[A-Za-z0-9_-]{11}`). Ignore extra query params (`list`, `t`, `si`). Reject playlist, channel, `@handle`, and `/results` URLs.

**Spotify track:** `open.spotify.com/track/<id>` and `open.spotify.com/intl-<locale>/track/<id>`. Optional query string is ignored. Reject album, playlist, artist, episode, show, user, and `spotify:` URIs that are not `spotify:track:<id>` (if a `spotify:track:` URI is pasted, treat it as a track).

### 4. YouTube paste

1. Parse the video id in-process. Do not search.
2. If that id is already in `source_choices[index]`, move that card to the front and set `pasted: true`.
3. Otherwise prepend `{ id, title, channel, duration, pasted: true }`. Cap at `PICKER_SOURCE_LIMIT` (9) by dropping leftover (non-pasted) cards from the end. If the list is already nine pasted cards, drop the last card.
4. Fill title, channel, and duration from a skip-download yt-dlp extract of `https://www.youtube.com/watch?v=<id>` when that extract succeeds. If it fails, still add the card: title `YouTube video`, channel empty, duration `null`.
5. Return the full list. Client re-renders from page one.

Preview GET and the later watch-URL download **omit** `match_filter` for `pasted: true` cards. Size cap, JS runtime, player clients, `noplaylist`, bundled FFmpeg ContextVar, and preview byte cap stay as they are.

`process_song` already pops `forced_sources[index]` for Use this source. Before downloading, read the matching `source_choices` card: if `pasted` is true, pass `skip_match_filter=True` into `download_song_from_youtube`. Leftover (non-pasted) Use this source still uses `match_filter`.

### 5. Spotify paste

1. GET `https://open.spotify.com/oembed?url=<canonical track URL>` with `allow_redirects=False`, timeouts in the same class as thumbnail fetch, and a small body cap (at or below artwork limits). Host must remain `open.spotify.com`.
2. Read JSON `title` (song) and `author_name` (artist). If `author_name` is missing, split `title` on the last ` - ` or ` by `. If title is still empty, 409.
3. Run the existing `extract_flat` YouTube search (`ytsearch{YOUTUBE_SEARCH_RESULTS}` + `build_youtube_search_query(artist, title)`).
4. Build leftovers with `collect_picker_sources(entries, tried_ids=set())` — same movie/clean/variant/duration filters, rank, and cap of nine. These cards are **not** pasted.
5. **Replace** `source_choices[index]` with that list. Return it.

Zero eligible hits: 409 `No YouTube matches for that Spotify track.` Do not replace the previous list.

oEmbed failure or non-JSON/non-200: 409 `Could not read that Spotify link.`

Do not call Spotify’s Web API. Do not download from Spotify.

### 6. Error handling

| Case | Result |
|---|---|
| Missing/invalid CSRF, no job, malformed JSON | Same 400 / 403 as `/choose-source` |
| Track not failed, or already queued | 409; dialog stays open; list unchanged |
| Not a Spotify track or YouTube video | 400: `Paste a Spotify track link or a YouTube video link.` |
| URL longer than 500 characters | 400, same copy |
| Spotify oEmbed fails or has no title/artist | 409: `Could not read that Spotify link.` |
| Spotify search yields zero leftover-eligible hits | 409: `No YouTube matches for that Spotify track.` Previous cards stay |
| YouTube id already in the list | 200; that card moves to the front and is marked pasted |
| YouTube metadata extract fails | 200; card still added with generic title |
| Rate limit | 429; existing too-many-requests toast |
| Use this source on a pasted id, then 403 | Failed; that id dropped; Choose source stays |
| Retry failed | Automatic search replaces the stored list, including pasted cards |
| Library-folder failure | Choose source stays hidden |

Isolation, byte caps, CSRF, job-local `source_choices`, and cleanup stay unchanged. Do not write paste state under `DATA_ROOT`.

## Testing

Mock yt-dlp and HTTP. Do not hit live YouTube or Spotify.

- Failed download with empty leftovers sets `can_choose_source` true and the choose-source fail message. Library-folder failure still does not.
- GET `/tracks/<index>/sources` on a failed empty list returns `{ "sources": [] }` and the dialog still opens.
- POST `/paste-source` YouTube watch/youtu.be/shorts prepends a `pasted` card; duplicate id moves to the front; list stays ≤ 9.
- Preview GET and watch-URL download for a pasted id omit `match_filter`. A leftover (non-pasted) id still has it.
- YouTube extract failure still 200s a generic card.
- Spotify oEmbed + mocked search replaces the list with leftover-filtered cards (not pasted). Zero hits → 409 and previous list unchanged. Playlist/album URL → 400.
- oEmbed is only `open.spotify.com`, `allow_redirects=False`.
- Non-failed index, forged job, and missing CSRF match `/choose-source`.
- Retry-failed replaces a pasted list with a new automatic leftover list.
- Existing choose-source, Load more, thumbnail, and preview tests still pass.
- HTML/JS: paste field and Add link exist; `app.js` POSTs `/paste-source`.

## Intended files

- `app.py` — `/paste-source`, URL parse helpers, `skip_match_filter` on download/preview, `can_choose_source` on all download failures
- `templates/index.html` — paste field and Add link
- `static/app.js` — Add link, busy state, re-render from response, clear on close
- `static/style.css` — paste row only if existing tokens are not enough
- `tests/test_app.py` — cases above

## Rollback

Revert the files above. In-memory pasted flags die with the job.

## Follow-up (not this batch)

Spotify album/playlist paste, or a separate paste control outside Choose source.
