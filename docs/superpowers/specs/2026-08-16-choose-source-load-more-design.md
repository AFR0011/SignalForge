# Choose Source Load More

**Date:** 2026-08-16
**Status:** Draft for review

## Goal

When automatic YouTube download fails, let the user page through more leftover hits from that same search. The dialog still opens with three cards. **Load more** appends the next three from a stored leftover list of at most nine.

Automatic download stays the default. **Start selected** and **Retry failed** do not change meaning. **Choose source** stays failure-only.

## Out of scope

- Changing which leftovers are eligible (movie, clean, remix, sub-90s, and 10+ minute hits stay dropped)
- Changing automatic YouTube ranking
- A second YouTube search, pasted watch URLs, or a YouTube embed
- Widening CSP `img-src` beyond `'self' data:`
- Revealing ids into the allow-list only after **Load more** (the stored leftover list is the allow-list)
- 409 on **Choose source** when the library folder is unusable
- Populated-browser / live-YouTube verification (RISK-013)

## Current behavior

On auto-fail, `collect_picker_sources` keeps leftover `extract_flat` hits after dropping tried ids and movie/clean/variant/duration junk, ranks them by view count then search order, and stores at most three on `Job.source_choices`. GET `/tracks/<index>/sources` returns that list. POST `/choose-source` and thumbnail GET accept only those stored 11-character ids. Search already requests `ytsearch15`.

## Design

### 1. Leftover storage

Reuse the existing leftover filters and ranking. Stop truncating to three. Cap the stored list at **nine**.

`collect_picker_sources(entries, tried_ids)` still:

1. Starts from that attempt’s `extract_flat` entries (up to 15).
2. Drops invalid ids, tried ids, duration `< 90` or `>= 600` when present, movie/scene titles, clean/non-explicit titles, and processed-variant titles.
3. Keeps label, lyric, soundtrack, music video, and visualizer hits that pass those filters.
4. Ranks by `view_count` descending, then original search order.
5. Returns at most nine records (`id`, `title`, `channel`, `duration`). `PICKER_SOURCE_LIMIT` becomes **9**. The dialog page size stays **3** (`PICKER_PAGE_SIZE`).

Store the full returned list on `Job.source_choices[index]` in memory. Do not write it under `DATA_ROOT`. Clear or replace it on the same events as today (success, new automatic attempt, chosen-id 403 for that id only, job replace/clear/TTL).

### 2. Routes

No new route.

**GET `/tracks/<index>/sources`** returns `{ "sources": [ ... ] }` for a failed index: the full stored leftover list (0–9 cards). Thumbnail URLs are still not stored; the client builds `/tracks/<index>/source-thumbs/<id>`.

**POST `/choose-source`** still accepts `{ "index", "video_id" }` only when `video_id` is in that stored list. CSRF, ownership, limiter, and 202 queue behavior stay unchanged.

**GET `/tracks/<index>/source-thumbs/<video_id>`** still serves a same-origin JPEG only for a stored id.

A client that POSTs an id from a not-yet-shown card is accepted if that id is in the stored list. Forged ids remain 409.

### 3. Dialog

The shared `#source-dialog` still shows song and artist, up to three cards at first open, **Use this source** per card, **Close**, and Escape.

**Load more** is a button in the dialog footer beside **Close**. Show it only when `sources.length` is greater than the number of cards already rendered. Clicking it appends the next `PICKER_PAGE_SIZE` leftovers, or the remainder if fewer than three are left (3 → 6 → 9 when nine are stored; 3 → 4 when four are stored). It does not start a download. After every stored leftover is visible, hide the button.

Fewer than four leftovers: no **Load more**. Zero leftovers: **Choose source** stays hidden and the fail message remains “Download failed. No alternate sources found.”

Closing and reopening the dialog starts at three cards again. The stored list does not change.

**Start selected** and **Retry failed** keep their current meaning. While the index is queued, pending, or downloading, **Choose source** and **Use this source** stay rejected as today.

### 4. Download path

Unchanged. A chosen leftover still downloads that watch URL with no second search. A 403 drops that id from `source_choices[index]` and leaves the rest. **Retry failed** still means automatic search and replaces the leftover list.

### 5. Error handling

| Case | Result |
|---|---|
| Fewer than four leftovers | No **Load more** |
| Empty leftover list | Hidden button; “No alternate sources found.” |
| Forged or unknown `video_id` | 409; row stays failed |
| Chosen source 403s | That id dropped; remaining leftovers stay; dialog pages over what is left |
| **Retry failed** | New automatic search; leftover list replaced |
| Thumbnail fetch fails | Card without image |
| Track not failed; job/CSRF missing | Existing 409 / 403 / 400 |

Isolation, byte caps, CSRF, CSP, and library write-through stay unchanged.

## Testing

Mock yt-dlp and HTTP. Do not hit live YouTube.

- After auto-fail, the job can store up to nine leftovers; a tenth passing leftover is not stored.
- GET `/tracks/<index>/sources` returns that full stored list, not only the first three.
- Existing leftover filters still drop tried ids, shorts, long files, movie, clean, and variant titles; label/lyric/soundtrack hits may still appear.
- Dialog first paint shows at most three cards; **Load more** appends three; a second click can reach nine; the button then hides.
- Reopening the dialog shows three cards again while GET still returns the full list.
- Forged id → 409. CSRF/ownership and thumbnail allow-list tests still pass.
- Chosen-id 403 still drops only that id.

## Intended files

- `app.py` — `PICKER_SOURCE_LIMIT = 9`; `collect_picker_sources` uses that cap. Page size 3 lives in `static/app.js` (or a small shared constant in the template) as `PICKER_PAGE_SIZE`.
- `templates/index.html` — **Load more** in the source dialog footer
- `static/app.js` — first three cards, append next three, hide **Load more** when exhausted
- `static/style.css` — footer layout only if existing tokens are not enough
- `tests/test_app.py` — nine-cap, GET full list, existing picker filter cases updated for the new cap

## Rollback

Revert the files above. Picker state is memory-only.
