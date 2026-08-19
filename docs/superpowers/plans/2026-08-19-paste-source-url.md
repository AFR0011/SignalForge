# Paste Spotify or YouTube Source URL Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a failed track’s Choose source dialog, let the user paste a Spotify track URL or a YouTube video URL; Spotify paste becomes a new leftover list and YouTube paste becomes one previewable card.

**Architecture:** `POST /paste-source` parses the URL, updates job-local `source_choices`, and returns the full list. Play / Use this source / Load more / thumbs / 30s preview keep using that list. Pasted YouTube cards set `pasted: true` so preview and watch-URL download omit `match_filter`. Choose source shows on every failed download, including empty leftovers.

**Tech Stack:** Flask, yt-dlp (mocked), requests oEmbed (mocked), vanilla JS, pytest.

## Global Constraints

- Picker is failure-only; **Start selected**, **Retry failed**, **Use this source**, **Load more**, and **Play** keep their current meaning.
- Do not embed YouTube or widen CSP (`media-src 'self'` already present).
- Do not add a Spotify API key or download audio from Spotify.
- Do not change leftover filters, ranking, `PICKER_SOURCE_LIMIT` (9), or `PICKER_PAGE_SIZE` (3).
- Do not hit live YouTube or Spotify in tests; mock yt-dlp and HTTP.
- `source_choices` stays process-local memory; never write paste state under `DATA_ROOT`.
- POST `/paste-source` does not queue a download (200, not 202).
- Existing YouTube `player_client` list stays `["web_embedded", "default", "-android_vr", "-ios", "-android_sdkless"]`.
- Keep the bundled FFmpeg ContextVar already used by `build_source_preview`.
- Library-folder failures still hide Choose source.

## File map

- `app.py` — URL parse, paste helpers, `skip_match_filter`, `can_choose_source` on download failures, `POST /paste-source`.
- `templates/index.html` — paste field and Add link.
- `static/app.js` — Add link, busy state, re-render, clear on close.
- `static/style.css` — paste row.
- `tests/test_app.py` — cases below.

Do not split `app.py`.

---

### Task 1: Parse pasted Spotify and YouTube URLs

**Files:**
- Modify: `app.py` (constants near `YOUTUBE_VIDEO_ID_RE`; helpers after `youtube_video_id`)
- Test: `tests/test_app.py` (after `test_preview_clip_path_uses_job_dir_and_video_id`)

**Interfaces:**
- Consumes: `youtube_video_id`, `urlparse` (already imported)
- Produces: `PASTE_URL_MAX_CHARS = 500`, `PASTE_INVALID_MESSAGE = "Paste a Spotify track link or a YouTube video link."`, `parse_pasted_source_url(value: str) -> dict[str, str] | None` returning `{"kind": "youtube", "id": "<11-char>"}` or `{"kind": "spotify", "url": "https://open.spotify.com/track/<id>"}`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_parse_pasted_source_url_accepts_youtube_and_spotify_tracks():
    youtube_urls = [
        "https://www.youtube.com/watch?v=labellabel1&list=PLxx&t=12",
        "https://youtu.be/labellabel1?si=abc",
        "https://www.youtube.com/shorts/labellabel1",
        "https://www.youtube.com/embed/labellabel1",
        "https://www.youtube.com/live/labellabel1",
        "https://music.youtube.com/watch?v=labellabel1",
        "https://m.youtube.com/watch?v=labellabel1",
    ]
    for url in youtube_urls:
        assert application.parse_pasted_source_url(url) == {"kind": "youtube", "id": "labellabel1"}
    assert application.parse_pasted_source_url(
        "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=xx"
    ) == {"kind": "spotify", "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"}
    assert application.parse_pasted_source_url(
        "https://open.spotify.com/intl-en/track/4cOdK2wGLETKBW3PvgPWqT"
    ) == {"kind": "spotify", "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"}
    assert application.parse_pasted_source_url(
        "spotify:track:4cOdK2wGLETKBW3PvgPWqT"
    ) == {"kind": "spotify", "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"}
    rejects = [
        "",
        "https://example.com/watch?v=labellabel1",
        "https://www.youtube.com/playlist?list=PLxx",
        "https://www.youtube.com/channel/UCxxxxxxxxxxxxxx",
        "https://www.youtube.com/@starling",
        "https://www.youtube.com/results?search_query=halo",
        "https://open.spotify.com/album/1abc",
        "https://open.spotify.com/playlist/1abc",
        "https://open.spotify.com/artist/1abc",
        "https://open.spotify.com/episode/1abc",
        "not a url",
        "x" * (application.PASTE_URL_MAX_CHARS + 1),
    ]
    for url in rejects:
        assert application.parse_pasted_source_url(url) is None
    assert application.PASTE_URL_MAX_CHARS == 500
    assert application.PASTE_INVALID_MESSAGE == "Paste a Spotify track link or a YouTube video link."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_app.py::test_parse_pasted_source_url_accepts_youtube_and_spotify_tracks`

Expected: FAIL (`parse_pasted_source_url` is not defined)

- [ ] **Step 3: Implement parser**

Add `import json` next to the other stdlib imports in `app.py`.

Near `YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")` add:

```python
PASTE_URL_MAX_CHARS = 500
PASTE_INVALID_MESSAGE = "Paste a Spotify track link or a YouTube video link."
_SPOTIFY_TRACK_ID_RE = re.compile(r"^[A-Za-z0-9]{10,32}$")
_YOUTUBE_HOSTS = {
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtu.be",
    "www.youtu.be",
}
```

After `youtube_video_id`:

```python
def parse_pasted_source_url(value: str) -> dict[str, str] | None:
    if not isinstance(value, str):
        return None
    raw = value.strip()
    if not raw or len(raw) > PASTE_URL_MAX_CHARS:
        return None
    if raw.lower().startswith("spotify:track:"):
        track_id = raw.split(":", 2)[-1].split("?")[0].strip()
        if _SPOTIFY_TRACK_ID_RE.fullmatch(track_id):
            return {"kind": "spotify", "url": f"https://open.spotify.com/track/{track_id}"}
        return None
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return None
    host = (parsed.hostname or "").lower()
    path = parsed.path or ""
    if host in {"youtu.be", "www.youtu.be"}:
        video_id = youtube_video_id(path.strip("/").split("/")[0] if path.strip("/") else "")
        if video_id is not None:
            return {"kind": "youtube", "id": video_id}
        return None
    if host in _YOUTUBE_HOSTS:
        parts = [part for part in path.split("/") if part]
        query = parsed.query
        video_id = None
        if parts[:1] == ["watch"] or path.endswith("/watch"):
            match = re.search(r"(?:^|&)v=([A-Za-z0-9_-]{11})(?:&|$)", f"&{query}&")
            if match:
                video_id = youtube_video_id(match.group(1))
        elif len(parts) >= 2 and parts[0] in {"shorts", "embed", "live"}:
            video_id = youtube_video_id(parts[1])
        if video_id is not None:
            return {"kind": "youtube", "id": video_id}
        return None
    if host == "open.spotify.com":
        parts = [part for part in path.split("/") if part]
        if parts and parts[0].startswith("intl-"):
            parts = parts[1:]
        if len(parts) >= 2 and parts[0] == "track":
            track_id = parts[1].split("?")[0]
            if _SPOTIFY_TRACK_ID_RE.fullmatch(track_id):
                return {"kind": "spotify", "url": f"https://open.spotify.com/track/{track_id}"}
        return None
    return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_app.py::test_parse_pasted_source_url_accepts_youtube_and_spotify_tracks`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Parse pasted Spotify and YouTube source URLs."
```

---

### Task 2: Show Choose source on every failed download

**Files:**
- Modify: `app.py` (`process_song` fail path near `can_choose = bool(job.source_choices.get(index))`)
- Test: `tests/test_app.py` (`test_process_song_empty_picker_stores_no_alternate_sources_message`, `test_never_fitting_pending_fails_closed_on_drain`; add empty-sources GET and last-id 403 cases)

**Interfaces:**
- Consumes: existing `process_song` fail handling, `failed_track_locked`, GET `/tracks/<index>/sources`
- Produces: non-library download failures set `can_choose_source` true and message `Download failed. You can retry this track or choose a source.` even when `source_choices` is empty. Library-folder failures stay `can_choose_source` false.

- [ ] **Step 1: Update and add failing tests**

Rename/replace `test_process_song_empty_picker_stores_no_alternate_sources_message` so it asserts the new message and `can_choose_source is True`. Keep the empty `source_choices` assertion.

```python
def test_process_song_empty_picker_still_allows_choose_source(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def fail_download(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        out = kwargs.get("picker_out")
        filled = kwargs.get("picker_filled")
        if out is not None:
            out.clear()
        if filled is not None:
            filled[0] = True
        raise application.DownloadError("No matching audio source found")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_download)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert 0 in job.failed
    assert not job.source_choices.get(0)
    assert job.statuses[0]["can_choose_source"] is True
    assert job.statuses[0]["message"] == "Download failed. You can retry this track or choose a source."
    listed = client.get("/tracks/0/sources")
    assert listed.status_code == 200
    assert listed.json == {"sources": []}
```

Add after the forced 403 test:

```python
def test_process_song_forced_403_on_last_id_still_allows_choose_source(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    job.source_choices[0] = [{"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201}]
    job.forced_sources[0] = "labellabel1"

    def fail_forced(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        raise application.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_forced)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert not job.source_choices.get(0)
    assert job.statuses[0]["can_choose_source"] is True
    assert "choose a source" in job.statuses[0]["message"]
```

In `test_never_fitting_pending_fails_closed_on_drain`, change the last two assertions to:

```python
    assert job.statuses[0]["message"] == "Download failed. You can retry this track or choose a source."
    assert job.statuses[0].get("can_choose_source") is True
```

Leave `test_process_song_library_move_failure_keeps_job_file` asserting `can_choose_source is False`.

Add:

```python
def test_process_song_automatic_retry_replaces_pasted_list(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201, "pasted": True},
    ]

    def fail_download(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        out = kwargs.get("picker_out")
        if out is not None:
            out.clear()
            out.extend([{
                "id": "newsource01",
                "title": "Halo Official Audio",
                "channel": "Label Records",
                "duration": 201,
            }])
        raise application.DownloadError("No matching audio source found")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_download)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert [item["id"] for item in job.source_choices[0]] == ["newsource01"]
    assert not job.source_choices[0][0].get("pasted")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_process_song_empty_picker_still_allows_choose_source tests/test_app.py::test_process_song_forced_403_on_last_id_still_allows_choose_source tests/test_app.py::test_process_song_automatic_retry_replaces_pasted_list tests/test_app.py::test_never_fitting_pending_fails_closed_on_drain`

Expected: FAIL (empty picker still sets `can_choose_source` false / old message)

- [ ] **Step 3: Change the fail path**

In `process_song`’s `except`, replace the `can_choose` / message block so non-library failures always allow Choose source. Keep leftover storage and 403 id-drop. Example:

```python
        with job.lock:
            job.failed.add(index)
            if keep_outputs:
                job.source_choices.pop(index, None)
                can_choose = False
            elif forced_id:
                if "403" in str(exc):
                    remaining = [
                        item for item in job.source_choices.get(index, [])
                        if item.get("id") != forced_id
                    ]
                    if remaining:
                        job.source_choices[index] = remaining
                    else:
                        job.source_choices.pop(index, None)
                can_choose = True
            elif picker_out:
                job.source_choices[index] = list(picker_out)
                can_choose = True
            else:
                can_choose = True
        if keep_outputs:
            message = str(exc) or "Could not save the file to the library folder."
        else:
            message = "Download failed. You can retry this track or choose a source."
```

Do not set `can_choose` from `bool(job.source_choices.get(index))` on download failures.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_process_song_empty_picker_still_allows_choose_source tests/test_app.py::test_process_song_forced_403_on_last_id_still_allows_choose_source tests/test_app.py::test_process_song_stores_picker_sources_and_can_choose_flag tests/test_app.py::test_process_song_library_move_failure_keeps_job_file tests/test_app.py::test_never_fitting_pending_fails_closed_on_drain tests/test_app.py::test_process_song_forced_watch_url_403_drops_that_picker_id tests/test_app.py::test_process_song_automatic_retry_replaces_pasted_list`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Show Choose source on every failed download."
```

---

### Task 3: Skip match_filter for pasted YouTube ids

**Files:**
- Modify: `app.py` (`download_song_from_youtube`, `build_source_preview`, `process_song` forced-id start, preview route)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `source_choices` cards may include `"pasted": true`
- Produces: `download_song_from_youtube(..., skip_match_filter: bool = False)`, `build_source_preview(..., skip_match_filter: bool = False)`. When true, options omit `match_filter`. `process_song` sets it from the matching card’s `pasted` flag. Preview route does the same.

- [ ] **Step 1: Write the failing tests**

```python
def test_forced_download_omits_match_filter_when_skip_requested(tmp_path, monkeypatch):
    output_base = tmp_path / "track"
    captured: dict[str, Any] = {}

    class FakeYDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, queries):
            captured["queries"] = queries
            output_base.with_suffix(".mp3").write_bytes(b"audio")

        def extract_info(self, _url, download=True):
            raise AssertionError("forced watch URL must not search")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    application.download_song_from_youtube(
        "Starling Halo",
        output_base,
        "ffmpeg",
        lambda *_args: None,
        100,
        watch_url="https://www.youtube.com/watch?v=labellabel1",
        skip_match_filter=True,
    )
    assert "match_filter" not in captured
    assert captured["queries"] == ["https://www.youtube.com/watch?v=labellabel1"]


def test_build_source_preview_omits_match_filter_when_skip_requested(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    captured: dict[str, Any] = {}

    class FakeYDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _queries):
            Path(captured["outtmpl"].replace(".%(ext)s", ".mp3")).write_bytes(b"ID3preview")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    result = application.build_source_preview(job_dir, "labellabel1", "ffmpeg", 100, skip_match_filter=True)
    assert result == job_dir / "preview-labellabel1.mp3"
    assert "match_filter" not in captured


def test_process_song_skips_match_filter_for_pasted_forced_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201, "pasted": True},
    ]
    job.forced_sources[0] = "labellabel1"
    captured: dict[str, Any] = {}

    def fake_download(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        captured["skip_match_filter"] = kwargs.get("skip_match_filter")
        captured["watch_url"] = kwargs.get("watch_url")
        output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "download_song_from_youtube", fake_download)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert captured["watch_url"] == "https://www.youtube.com/watch?v=labellabel1"
    assert captured["skip_match_filter"] is True
```

Also add this sibling for the preview route (do not weaken `test_source_preview_route_serves_cached_clip_for_stored_id`; leftover cards must still omit `skip_match_filter` or pass false):

```python
def test_source_preview_route_skips_match_filter_for_pasted_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {
        "status": "failed",
        "index": 0,
        "job_id": job.job_id,
        "message": "failed",
        "can_choose_source": True,
    }
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201, "pasted": True},
    ]
    captured: dict[str, Any] = {}

    def fake_build(job_directory, video_id, ffmpeg_path, max_source_bytes, skip_match_filter=False):
        captured["skip_match_filter"] = skip_match_filter
        path = application.preview_clip_path(job_directory, video_id)
        path.write_bytes(b"ID3clip")
        return path

    monkeypatch.setattr(application, "build_source_preview", fake_build)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    ok = client.get("/tracks/0/source-previews/labellabel1")
    assert ok.status_code == 200
    assert captured["skip_match_filter"] is True
```

Existing `test_source_limit_is_passed_to_ytdlp_and_equality_is_allowed` already asserts default downloads still pass `match_filter`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_forced_download_omits_match_filter_when_skip_requested tests/test_app.py::test_build_source_preview_omits_match_filter_when_skip_requested tests/test_app.py::test_process_song_skips_match_filter_for_pasted_forced_id tests/test_app.py::test_source_preview_route_skips_match_filter_for_pasted_id`

Expected: FAIL (`skip_match_filter` unexpected kwarg)

- [ ] **Step 3: Implement skip flag**

Add `skip_match_filter: bool = False` to `download_song_from_youtube` and `build_source_preview`. After building `download_options` / preview `options`, if `skip_match_filter`: `options.pop("match_filter", None)`.

In `process_song`, when popping `forced_id`, read the pasted flag **before** download:

```python
    with job.lock:
        forced_id = job.forced_sources.pop(index, "")
        skip_match_filter = False
        if forced_id:
            for item in job.source_choices.get(index) or []:
                if item.get("id") == forced_id and item.get("pasted"):
                    skip_match_filter = True
                    break
        else:
            job.source_choices.pop(index, None)
```

Pass `skip_match_filter=skip_match_filter` into `download_song_from_youtube`.

In `track_source_preview`, after the allow-list check, compute `skip_match_filter` from the matching stored card’s `pasted` flag and pass it to `build_source_preview`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_forced_download_omits_match_filter_when_skip_requested tests/test_app.py::test_build_source_preview_omits_match_filter_when_skip_requested tests/test_app.py::test_process_song_skips_match_filter_for_pasted_forced_id tests/test_app.py::test_source_preview_route_skips_match_filter_for_pasted_id tests/test_app.py::test_download_watch_url_skips_search_and_uses_that_url tests/test_app.py::test_build_source_preview_writes_bounded_mp3_without_library_or_retain tests/test_app.py::test_source_preview_route_serves_cached_clip_for_stored_id tests/test_app.py::test_source_limit_is_passed_to_ytdlp_and_equality_is_allowed`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Skip match filters for pasted YouTube sources."
```

---

### Task 4: Build pasted YouTube and Spotify picker lists

**Files:**
- Modify: `app.py` (helpers after `parse_pasted_source_url` / `collect_picker_sources`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `parse_pasted_source_url`, `collect_picker_sources`, `PICKER_SOURCE_LIMIT`, `YoutubeDL`, `build_youtube_search_query`, `YOUTUBE_SEARCH_RESULTS`, `resolve_js_runtime`, `requests`, `_read_limited_response`
- Produces:
  - `merge_pasted_youtube_choice(choices: list[dict[str, Any]], card: dict[str, Any]) -> list[dict[str, Any]]`
  - `fetch_youtube_paste_card(video_id: str) -> dict[str, Any]`
  - `fetch_spotify_picker_sources(track_url: str, max_bytes: int) -> list[dict[str, Any]] | None` (`None` = oEmbed unreadable; `[]` = no leftover-eligible hits)

- [ ] **Step 1: Write the failing tests**

```python
def test_merge_pasted_youtube_choice_prepends_dedupes_and_caps():
    leftovers = [
        {"id": f"pick{i:07d}", "title": "Halo", "channel": "Starling", "duration": 200}
        for i in range(9)
    ]
    card = {"id": "labellabel1", "title": "Halo Audio", "channel": "Label", "duration": 201}
    merged = application.merge_pasted_youtube_choice(leftovers, card)
    assert merged[0]["id"] == "labellabel1"
    assert merged[0]["pasted"] is True
    assert len(merged) == 9
    assert merged[-1]["id"] == "pick0000007"
    again = application.merge_pasted_youtube_choice(merged, {"id": "pick0000000", "title": "Halo"})
    assert again[0]["id"] == "pick0000000"
    assert again[0]["pasted"] is True
    assert [item["id"] for item in again].count("pick0000000") == 1


def test_fetch_youtube_paste_card_uses_extract_or_generic(monkeypatch):
    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download=False):
            assert download is False
            assert url.endswith("labellabel1")
            return {
                "id": "labellabel1",
                "title": "Halo (Official Audio)",
                "uploader": "Starling - Topic",
                "duration": 255,
            }

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    card = application.fetch_youtube_paste_card("labellabel1")
    assert card == {
        "id": "labellabel1",
        "title": "Halo (Official Audio)",
        "channel": "Starling - Topic",
        "duration": 255,
        "pasted": True,
    }

    class FailYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            raise application.DownloadError("403")

    monkeypatch.setattr(application, "YoutubeDL", FailYDL)
    fallback = application.fetch_youtube_paste_card("labellabel1")
    assert fallback == {
        "id": "labellabel1",
        "title": "YouTube video",
        "channel": "",
        "duration": None,
        "pasted": True,
    }


def test_fetch_spotify_picker_sources_oembed_and_leftover_filters(monkeypatch):
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
        url = "https://open.spotify.com/oembed?url=https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
        headers = {"Content-Type": "application/json", "Content-Length": "80"}

        def iter_content(self, _size):
            yield b'{"title": "Halo", "author_name": "Starling"}'

        def close(self):
            return None

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["params"] = kwargs.get("params")
        captured["allow_redirects"] = kwargs.get("allow_redirects")
        return FakeResponse()

    class FakeYDL:
        def __init__(self, options):
            captured["search"] = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, url, download=False):
            captured["search_url"] = url
            return {"entries": [
                {"id": "labellabel1", "title": "Halo Official Audio", "uploader": "Label Records", "duration": 201, "view_count": 9},
                {"id": "previewxx01", "title": "Halo Preview", "uploader": "User", "duration": 20},
            ]}

    monkeypatch.setattr(application.requests, "get", fake_get)
    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    sources = application.fetch_spotify_picker_sources(
        "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
        200_000,
    )
    assert captured["url"] == "https://open.spotify.com/oembed"
    assert captured["params"]["url"] == "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"
    assert captured["allow_redirects"] is False
    assert "Halo" in captured["search_url"] and "Starling" in captured["search_url"]
    assert [item["id"] for item in sources] == ["labellabel1"]
    assert "pasted" not in sources[0]

    class EmptyYDL:
        def __init__(self, options):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=False):
            return {"entries": []}

    monkeypatch.setattr(application, "YoutubeDL", EmptyYDL)
    assert application.fetch_spotify_picker_sources(
        "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
        200_000,
    ) == []

    class BadResponse:
        status_code = 404
        url = "https://open.spotify.com/oembed"
        headers = {}

        def iter_content(self, _size):
            yield b""

        def close(self):
            return None

    monkeypatch.setattr(application.requests, "get", lambda *_a, **_k: BadResponse())
    assert application.fetch_spotify_picker_sources(
        "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT",
        200_000,
    ) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_merge_pasted_youtube_choice_prepends_dedupes_and_caps tests/test_app.py::test_fetch_youtube_paste_card_uses_extract_or_generic tests/test_app.py::test_fetch_spotify_picker_sources_oembed_and_leftover_filters`

Expected: FAIL (helpers not defined)

- [ ] **Step 3: Implement helpers**

```python
def merge_pasted_youtube_choice(choices: list[dict[str, Any]], card: dict[str, Any]) -> list[dict[str, Any]]:
    video_id = youtube_video_id(str(card.get("id") or ""))
    if video_id is None:
        return list(choices)
    pasted = {**card, "id": video_id, "pasted": True}
    rest = [item for item in choices if item.get("id") != video_id]
    return [pasted, *rest][:PICKER_SOURCE_LIMIT]


def fetch_youtube_paste_card(video_id: str) -> dict[str, Any]:
    bound = youtube_video_id(video_id)
    fallback = {"id": bound or "", "title": "YouTube video", "channel": "", "duration": None, "pasted": True}
    if bound is None:
        return fallback
    runtime_name, runtime_path = resolve_js_runtime()
    options = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        "js_runtimes": {runtime_name: {"path": runtime_path}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "default", "-android_vr", "-ios", "-android_sdkless"],
            }
        },
    }
    try:
        with YoutubeDL(options) as downloader:
            info = downloader.extract_info(f"https://www.youtube.com/watch?v={bound}", download=False) or {}
    except DownloadError:
        return fallback
    duration = info.get("duration")
    duration_value = int(duration) if isinstance(duration, (int, float)) and not isinstance(duration, bool) else None
    return {
        "id": bound,
        "title": str(info.get("title") or "YouTube video"),
        "channel": str(info.get("uploader") or info.get("channel") or ""),
        "duration": duration_value,
        "pasted": True,
    }


def _spotify_title_artist(payload: dict[str, Any]) -> tuple[str, str] | None:
    title = str(payload.get("title") or "").strip()
    artist = str(payload.get("author_name") or "").strip()
    if not artist:
        for separator in (" - ", " by "):
            if separator in title:
                title, artist = (part.strip() for part in title.rsplit(separator, 1))
                break
    if not title:
        return None
    return title, artist


def fetch_spotify_picker_sources(track_url: str, max_bytes: int) -> list[dict[str, Any]] | None:
    try:
        response = requests.get(
            "https://open.spotify.com/oembed",
            params={"url": track_url},
            timeout=(3.05, 8),
            stream=True,
            allow_redirects=False,
        )
        if response.status_code != 200:
            return None
        host = urlparse(response.url).hostname
        if host != "open.spotify.com":
            return None
        data = json.loads(_read_limited_response(response, max_bytes))
        if not isinstance(data, dict):
            return None
        parsed = _spotify_title_artist(data)
        if parsed is None:
            return None
        title, artist = parsed
    except (requests.RequestException, ValueError, json.JSONDecodeError, UnicodeDecodeError):
        return None
    runtime_name, runtime_path = resolve_js_runtime()
    search_url = f"ytsearch{YOUTUBE_SEARCH_RESULTS}:{build_youtube_search_query(artist, title)}"
    with YoutubeDL({
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
        "js_runtimes": {runtime_name: {"path": runtime_path}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "default", "-android_vr", "-ios", "-android_sdkless"],
            }
        },
    }) as explorer:
        listing = explorer.extract_info(search_url, download=False) or {}
    entries = [entry for entry in listing.get("entries") or [] if isinstance(entry, dict)]
    return collect_picker_sources(entries, set())
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_merge_pasted_youtube_choice_prepends_dedupes_and_caps tests/test_app.py::test_fetch_youtube_paste_card_uses_extract_or_generic tests/test_app.py::test_fetch_spotify_picker_sources_oembed_and_leftover_filters`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Resolve pasted YouTube and Spotify links into picker cards."
```

---

### Task 5: POST `/paste-source`

**Files:**
- Modify: `app.py` (`create_app` routes, next to `choose_source`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `mutation_job`, `failed_track_locked`, `parse_pasted_source_url`, `merge_pasted_youtube_choice`, `fetch_youtube_paste_card`, `fetch_spotify_picker_sources`, `SOURCE_THUMB_MAX_BYTES`, `ARTWORK_MAX_BYTES`
- Produces: `POST /paste-source` limiter `20 per minute`, CSRF JSON `{ index, url }` → 200 `{ sources }` or 400/403/409. Does not call `queue_indices`.

- [ ] **Step 1: Write the failing tests**

```python
def test_paste_source_youtube_and_spotify_and_rejects(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    token = csrf_for(app, client)
    job.failed.add(0)
    job.statuses[0] = {
        "job_id": job.job_id,
        "index": 0,
        "status": "failed",
        "message": "failed",
        "can_choose_source": True,
    }
    job.source_choices[0] = [
        {"id": f"pick{i:07d}", "title": "Halo", "channel": "Starling", "duration": 200}
        for i in range(3)
    ]
    monkeypatch.setattr(
        application,
        "fetch_youtube_paste_card",
        lambda video_id: {
            "id": video_id,
            "title": "Halo Audio",
            "channel": "Label",
            "duration": 201,
            "pasted": True,
        },
    )
    no_csrf = client.post("/paste-source", json={"index": 0, "url": "https://youtu.be/labellabel1"})
    assert no_csrf.status_code == 400
    bad = client.post(
        "/paste-source",
        json={"index": 0, "url": "https://open.spotify.com/playlist/abc"},
        headers={"X-CSRFToken": token},
    )
    assert bad.status_code == 400
    assert bad.json["error"] == application.PASTE_INVALID_MESSAGE
    queued = client.post(
        "/paste-source",
        json={"index": 0, "url": "https://youtu.be/labellabel1"},
        headers={"X-CSRFToken": token},
    )
    # index 0 is failed, should 200
    assert queued.status_code == 200
    assert queued.json["sources"][0]["id"] == "labellabel1"
    assert queued.json["sources"][0]["pasted"] is True
    assert job.source_choices[0][0]["id"] == "labellabel1"
    assert client.get("/tracks/0/sources").json["sources"][0]["id"] == "labellabel1"

    previous = list(job.source_choices[0])
    monkeypatch.setattr(application, "fetch_spotify_picker_sources", lambda *_a, **_k: None)
    unread = client.post(
        "/paste-source",
        json={"index": 0, "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"},
        headers={"X-CSRFToken": token},
    )
    assert unread.status_code == 409
    assert unread.json["error"] == "Could not read that Spotify link."
    assert job.source_choices[0] == previous

    monkeypatch.setattr(application, "fetch_spotify_picker_sources", lambda *_a, **_k: [])
    empty = client.post(
        "/paste-source",
        json={"index": 0, "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"},
        headers={"X-CSRFToken": token},
    )
    assert empty.status_code == 409
    assert empty.json["error"] == "No YouTube matches for that Spotify track."
    assert job.source_choices[0] == previous

    monkeypatch.setattr(
        application,
        "fetch_spotify_picker_sources",
        lambda *_a, **_k: [{"id": "newsource01", "title": "Halo", "channel": "Label", "duration": 200}],
    )
    replaced = client.post(
        "/paste-source",
        json={"index": 0, "url": "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT"},
        headers={"X-CSRFToken": token},
    )
    assert replaced.status_code == 200
    assert [item["id"] for item in replaced.json["sources"]] == ["newsource01"]
    assert "pasted" not in replaced.json["sources"][0]

    job.statuses[0]["status"] = "queued"
    job.failed.discard(0)
    not_failed = client.post(
        "/paste-source",
        json={"index": 0, "url": "https://youtu.be/labellabel1"},
        headers={"X-CSRFToken": token},
    )
    assert not_failed.status_code == 409
```

CSRF-missing is already in the test above. `mutation_job` returns 403 without a session job, same as `/choose-source`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_app.py::test_paste_source_youtube_and_spotify_and_rejects`

Expected: FAIL (404, no `/paste-source`)

- [ ] **Step 3: Add the route**

Next to `choose_source`:

```python
    @flask_app.route("/paste-source", methods=["POST"])
    @limiter.limit("20 per minute")
    def paste_source() -> Any:
        job, error_response = mutation_job()
        if error_response:
            return error_response
        assert job is not None
        payload = request.get_json(silent=True) or {}
        try:
            index = int(payload.get("index"))
        except (TypeError, ValueError):
            return jsonify(error="Selection is invalid"), 400
        raw_url = payload.get("url")
        parsed = parse_pasted_source_url(str(raw_url if isinstance(raw_url, str) else ""))
        if parsed is None:
            return jsonify(error=PASTE_INVALID_MESSAGE), 400
        with job.lock:
            if not failed_track_locked(job, index):
                return jsonify(error="Choose a source only for a failed track"), 409
        if parsed["kind"] == "youtube":
            card = fetch_youtube_paste_card(parsed["id"])
            with job.lock:
                if not failed_track_locked(job, index):
                    return jsonify(error="Choose a source only for a failed track"), 409
                updated = merge_pasted_youtube_choice(list(job.source_choices.get(index) or []), card)
                job.source_choices[index] = updated
                sources = list(updated)
            return jsonify(sources=sources)
        max_bytes = min(SOURCE_THUMB_MAX_BYTES, int(flask_app.config["ARTWORK_MAX_BYTES"]))
        fetched = fetch_spotify_picker_sources(parsed["url"], max_bytes)
        if fetched is None:
            return jsonify(error="Could not read that Spotify link."), 409
        if not fetched:
            return jsonify(error="No YouTube matches for that Spotify track."), 409
        with job.lock:
            if not failed_track_locked(job, index):
                return jsonify(error="Choose a source only for a failed track"), 409
            job.source_choices[index] = list(fetched)
            sources = list(fetched)
        return jsonify(sources=sources)
```

Do not queue a download. Do not write under `DATA_ROOT`.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_paste_source_youtube_and_spotify_and_rejects tests/test_app.py::test_choose_source_routes_require_failed_stored_id tests/test_app.py::test_sources_route_returns_all_stored_leftovers`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Add a paste-source route for failed tracks."
```

---

### Task 6: Paste field in the Choose source dialog

**Files:**
- Modify: `templates/index.html` (`#source-dialog`)
- Modify: `static/app.js` (dialog wiring)
- Modify: `static/style.css` (paste row)
- Test: `tests/test_app.py` (HTML/JS contract next to `test_source_dialog_preview_play_is_a_non_submit_button`)

**Interfaces:**
- Consumes: `POST /paste-source` 200 `{ sources }`, existing `mutate`, `storedSources`, `shownCount`, `renderNextSourcePage`, `finalizeSourceDialogClose`
- Produces: `#source-dialog-url`, `#source-dialog-paste` Add link; success replaces cards from page one and clears the input; errors leave cards and announce; Enter in the field does not close the dialog.

- [ ] **Step 1: Write the failing test**

```python
def test_source_dialog_paste_field_posts_paste_source():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    assert 'id="source-dialog-url"' in html
    assert 'placeholder="Paste a Spotify or YouTube link"' in html
    assert 'id="source-dialog-paste" type="button"' in html
    assert "Add link" in html
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "/paste-source" in js
    assert "source-dialog-paste" in js
    assert "source-dialog-url" in js
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert ".source-paste" in css
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_app.py::test_source_dialog_paste_field_posts_paste_source`

Expected: FAIL (paste field missing)

- [ ] **Step 3: Implement UI**

In `templates/index.html`, above `#source-dialog-cards`:

```html
        <p id="source-dialog-meta"></p>
        <div class="source-paste">
          <input id="source-dialog-url" type="url" maxlength="500" placeholder="Paste a Spotify or YouTube link" autocomplete="off">
          <button class="button button-quiet" id="source-dialog-paste" type="button">Add link</button>
        </div>
        <div id="source-dialog-cards" class="source-cards"></div>
```

In `static/style.css` after `.source-dialog-chrome`:

```css
.source-paste { display: flex; gap: 8px; flex-wrap: wrap; align-items: center; margin: 12px 0 0; }
.source-paste input {
  flex: 1 1 220px;
  min-width: 0;
  padding: 8px 10px;
  color: var(--ink);
  background: var(--panel-2);
  border: 1px solid var(--line);
  border-radius: 8px;
}
```

In `static/app.js`, next to `sourceMore` / `sourceAudio`:

```javascript
  const sourcePaste = document.getElementById("source-dialog-paste");
  const sourceUrl = document.getElementById("source-dialog-url");
```

Clear the field in `finalizeSourceDialogClose`:

```javascript
    if (sourceUrl) sourceUrl.value = "";
```

Add helpers to disable/enable paste controls during Add link (field, Add link, Load more, all `.source-cards button`):

```javascript
  const setSourcePasteBusy = (busy) => {
    if (sourceUrl) sourceUrl.disabled = busy;
    if (sourcePaste) sourcePaste.disabled = busy;
    if (sourceMore) sourceMore.disabled = busy;
    sourceCards?.querySelectorAll("button").forEach((btn) => {
      btn.disabled = busy;
    });
  };
```

Replace cards from a full list:

```javascript
  const replaceSourceCards = (index, sources) => {
    storedSources = sources || [];
    shownCount = 0;
    sourceDialogIndex = index;
    if (sourceCards) sourceCards.replaceChildren();
    if (sourceMore) sourceMore.disabled = false;
    renderNextSourcePage(index);
  };
```

Wire Add link (and Enter on the input). Use `mutate("/paste-source", { headers: { "Content-Type": "application/json" }, body: JSON.stringify({ index: sourceDialogIndex, url: sourceUrl.value }) })`. On success, `replaceSourceCards(sourceDialogIndex, data.sources)` and `sourceUrl.value = ""`. On error, do not clear cards; `announce(error.status === 429 ? "Too many requests. Wait a moment and try again." : error.message, "error")`. `event.preventDefault()` on Enter so `method="dialog"` does not close.

While Add link runs, `setSourcePasteBusy(true)` and restore `false` in `finally`, then `updateLoadMoreVisibility()`.

Empty leftover GET already returns `[]`; `renderNextSourcePage` should leave the paste field visible (it is not inside `#source-dialog-cards`). Do not hide Choose source when `sources` is empty — Task 2 already sets the flag.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_source_dialog_paste_field_posts_paste_source tests/test_app.py::test_source_dialog_load_more_is_a_non_submit_button tests/test_app.py::test_source_dialog_preview_play_is_a_non_submit_button tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract`

Then: `python -m pytest -q`, `python -m py_compile app.py`, `node --check static/app.js`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/app.js static/style.css tests/test_app.py
git commit -m "Add a paste field to the Choose source dialog."
```

---

## Spec coverage

| Spec section | Task |
|---|---|
| Choose source on every failed download; empty leftovers; library still hidden | 2 |
| Fail message always choose-source (non-library) | 2 |
| 403 drops id; Choose source stays | 2 |
| Retry failed replaces list including pasted | 2 (`test_process_song_automatic_retry_replaces_pasted_list`) |
| Dialog paste field, Add link, busy, clear on close, Enter | 6 |
| POST `/paste-source` CSRF, 20/min, 200 sources, no queue | 5 |
| YouTube URL parse | 1 |
| YouTube prepend/dedupe/cap 9, extract or generic card | 4, 5 |
| Pasted skip `match_filter` on preview and download | 3 |
| Spotify track oEmbed, leftover replace, zero-hit 409 | 4, 5 |
| Reject playlist/album/non-track | 1, 5 |
| URL length 500 | 1, 6 (`maxlength`) |
| Tests mock HTTP/yt-dlp | 4, 5 |
| HTML/JS contract | 6 |
