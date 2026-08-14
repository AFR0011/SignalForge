# Choose Source On Failure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** After automatic YouTube download fails, let the user pick one of up to three remaining search hits for that track and download it through the existing job.

**Architecture:** Automatic search/rank/download stays the default. On failure, `download_song_from_youtube` fills a leftover picker list from the same `extract_flat` results (excluding tried ids and junk durations/titles). That list lives only on `Job.source_choices`. The UI opens a native `<dialog>` and POSTs a stored 11-character video id; `process_song` then downloads that watch URL with no second search. Thumbnails are same-origin proxies of `https://i.ytimg.com/vi/<id>/hqdefault.jpg` for ids already on that failed track.

**Tech Stack:** Flask, Flask-SocketIO, yt-dlp (mocked in tests), Requests, Jinja, vanilla JS, pytest.

## Global Constraints

- Picker is failure-only; **Start selected** and **Retry failed** keep their current meaning.
- Accept only an 11-character YouTube id (`[A-Za-z0-9_-]{11}`) that is already in that track’s stored list; never a pasted URL.
- Do not widen CSP `img-src` beyond `'self' data:`.
- Do not hit live YouTube or iTunes in tests; mock yt-dlp and HTTP.
- `source_choices` and `forced_sources` are process-local memory on `Job`; never write them under `DATA_ROOT`.
- POST `/choose-source` uses the same CSRF/ownership rules and `20 per minute` limiter as `/download`.
- GET `/tracks/<index>/sources` and GET `/tracks/<index>/source-thumbs/<video_id>` use `60 per minute`.
- Store at most three picker records: `id`, `title`, `channel`, `duration` (`None` if missing).
- Existing isolation, byte caps, one-worker process-local jobs, and in-attempt auto 403 fallback stay unchanged.

## File map

- `app.py` — picker helpers, `watch_url` / `picker_out` on download, `Job` fields, `process_song` persistence, three new routes, thumbnail fetch.
- `templates/index.html` — **Choose source** button and one shared `<dialog>`.
- `static/app.js` — open/close dialog, fetch cards, POST choice, row state.
- `static/style.css` — dialog and card layout using existing color tokens.
- `tests/test_app.py` — mocked unit/route tests.
- `README.md` — one sentence that failed tracks can choose an alternate source.

Do not split `app.py`; follow the existing single-module pattern.

---

### Task 1: Picker list helper

**Files:**
- Modify: `app.py` (after `youtube_watch_url`, around line 1050)
- Test: `tests/test_app.py` (after `test_select_youtube_source_skips_movie_clips_and_allows_trusted_fallbacks`)

**Interfaces:**
- Consumes: `_MOVIE_TITLE`, `_CLEAN_TITLE`, `_VARIANT_TITLE`, `_entry_view_count`, `youtube_watch_url`
- Produces: `YOUTUBE_VIDEO_ID_RE`, `PICKER_SOURCE_LIMIT = 3`, `youtube_video_id(value: str) -> str | None`, `collect_picker_sources(entries: list[dict[str, Any]], tried_ids: set[str]) -> list[dict[str, Any]]`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_app.py`:

```python
def test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk():
    entries = [
        {"id": "triedtried1", "title": "Halo (Official Audio)", "uploader": "Starling", "duration": 200, "view_count": 9_000_000},
        {"id": "shortshort1", "title": "Halo", "uploader": "Starling", "duration": 21, "view_count": 50},
        {"id": "longlonglng", "title": "Halo", "uploader": "Starling", "duration": 600, "view_count": 80},
        {"id": "moviemovie1", "title": "Halo movie scene", "uploader": "Starling", "duration": 200, "view_count": 70},
        {"id": "cleanclean1", "title": "Halo (Clean Version)", "uploader": "Starling", "duration": 200, "view_count": 60},
        {"id": "parodyparod", "title": "Halo (Parody)", "uploader": "Starling", "duration": 200, "view_count": 55},
        {"id": "labellabel1", "title": "Starling - Halo (Official Audio)", "uploader": "Label Records", "duration": 201, "view_count": 500_000},
        {"id": "lyriclyric1", "title": "Halo (Lyric Video)", "uploader": "Starling", "duration": 202, "view_count": 100_000},
        {"id": "soundtracks", "title": "Halo", "uploader": "Halo Soundtrack", "duration": 199, "view_count": 250_000},
        {"id": "noduration1", "title": "Halo", "uploader": "Other Channel", "duration": None, "view_count": 10},
        {"id": "bad", "title": "Halo", "uploader": "X", "duration": 200, "view_count": 999_999_999},
    ]
    picked = application.collect_picker_sources(entries, {"triedtried1"})
    ids = [item["id"] for item in picked]
    assert ids == ["labellabel1", "soundtracks", "lyriclyric1"]
    assert picked[0] == {
        "id": "labellabel1",
        "title": "Starling - Halo (Official Audio)",
        "channel": "Label Records",
        "duration": 201,
    }
    assert application.youtube_video_id("bad") is None
    assert application.youtube_video_id("labellabel1") == "labellabel1"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_app.py::test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk`

Expected: FAIL with `AttributeError: module 'app' has no attribute 'collect_picker_sources'`

- [ ] **Step 3: Write minimal implementation**

In `app.py` next to `youtube_watch_url`:

```python
YOUTUBE_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
PICKER_SOURCE_LIMIT = 3


def youtube_video_id(value: str) -> str | None:
    if isinstance(value, str) and YOUTUBE_VIDEO_ID_RE.fullmatch(value):
        return value
    return None


def collect_picker_sources(entries: list[dict[str, Any]], tried_ids: set[str]) -> list[dict[str, Any]]:
    ranked: list[tuple[int, int, dict[str, Any]]] = []
    for order, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        video_id = youtube_video_id(str(entry.get("id") or ""))
        if video_id is None or video_id in tried_ids:
            continue
        duration = entry.get("duration")
        if isinstance(duration, (int, float)) and not isinstance(duration, bool):
            if duration < 90 or duration >= 600:
                continue
            duration_value: int | None = int(duration)
        else:
            duration_value = None
        title = str(entry.get("title") or "")
        if _MOVIE_TITLE.search(title) or _CLEAN_TITLE.search(title) or _VARIANT_TITLE.search(title):
            continue
        ranked.append((_entry_view_count(entry), -order, {
            "id": video_id,
            "title": title,
            "channel": str(entry.get("uploader") or entry.get("channel") or ""),
            "duration": duration_value,
        }))
    ranked.sort(reverse=True)
    return [item[2] for item in ranked[:PICKER_SOURCE_LIMIT]]
```

Keep `youtube_watch_url` using `youtube_video_id` for the 11-character branch so there is one id rule.

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest -q tests/test_app.py::test_collect_picker_sources_keeps_label_hits_and_drops_tried_or_junk tests/test_app.py::test_select_youtube_source_skips_movie_clips_and_allows_trusted_fallbacks`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Add leftover YouTube picker ranking for failed downloads."
```

---

### Task 2: Direct watch URL and leftover picker on auto-fail

**Files:**
- Modify: `app.py` (`download_song_from_youtube`, currently starting at line 1201)
- Test: `tests/test_app.py` (near `test_youtube_download_retries_next_result_after_403`)

**Interfaces:**
- Consumes: `collect_picker_sources`, `youtube_watch_url`, `rank_youtube_sources`
- Produces: `download_song_from_youtube(..., watch_url: str = "", picker_out: list[dict[str, Any]] | None = None) -> None`. On auto-fail, `picker_out` is cleared then extended with leftover sources. When `watch_url` is set, skip search/ranking and do not mutate `picker_out`.

- [ ] **Step 1: Write the failing tests**

```python
def test_download_watch_url_skips_search_and_uses_that_url(tmp_path, monkeypatch):
    output_base = tmp_path / "track"
    calls: list[str] = []

    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=True):
            raise AssertionError("forced watch URL must not search")

        def download(self, queries):
            calls.append(queries[0])
            output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    picker: list[dict] = [{"id": "shouldstay11"}]
    application.download_song_from_youtube(
        "Starling Halo",
        output_base,
        "ffmpeg",
        lambda *_args: None,
        100,
        artist="Starling",
        title="Halo",
        watch_url="https://www.youtube.com/watch?v=labellabel1",
        picker_out=picker,
    )
    assert calls == ["https://www.youtube.com/watch?v=labellabel1"]
    assert picker == [{"id": "shouldstay11"}]
    assert output_base.with_suffix(".mp3").is_file()


def test_auto_download_failure_fills_picker_excluding_tried_ids(tmp_path, monkeypatch):
    output_base = tmp_path / "track"

    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def extract_info(self, _url, download=True):
            return {
                "entries": [
                    {"id": "official111", "title": "Halo Official Audio", "uploader": "Starling - Topic", "duration": 200, "view_count": 9},
                    {"id": "labellabel1", "title": "Starling - Halo (Official Audio)", "uploader": "Label Records", "duration": 201, "view_count": 500_000},
                ]
            }

        def download(self, queries):
            raise application.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    picker: list[dict] = [{"id": "stale"}]
    with pytest.raises(application.DownloadError, match="403"):
        application.download_song_from_youtube(
            "Starling Halo",
            output_base,
            "ffmpeg",
            lambda *_args: None,
            100,
            artist="Starling",
            title="Halo",
            picker_out=picker,
        )
    assert [item["id"] for item in picker] == ["labellabel1"]
```

If `"official111"` is not 11 characters, use `"official111"` → change to `"officialaaa"` (11 chars) in both the test and FakeYDL entries. All ids in this test must be exactly 11 characters: `"officialaaa"` and `"labellabel1"`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_download_watch_url_skips_search_and_uses_that_url tests/test_app.py::test_auto_download_failure_fills_picker_excluding_tried_ids`

Expected: FAIL (`watch_url` unexpected keyword or picker stays stale)

- [ ] **Step 3: Write minimal implementation**

Change the signature and body of `download_song_from_youtube`:

```python
def download_song_from_youtube(
    query: str,
    output_base: Path,
    ffmpeg_path: str,
    progress: Callable[[float | None, str], None],
    max_source_bytes: int,
    *,
    artist: str = "",
    title: str = "",
    watch_url: str = "",
    picker_out: list[dict[str, Any]] | None = None,
) -> None:
```

Keep `progress_hook` and `shared` as they are today.

When `watch_url` is non-empty, skip `extract_info` / ranking. Build `download_options` as today and download `[watch_url]` only. On success, prepare sidecar JPEG and return. Do not write `picker_out`. Re-raise `DownloadError` with the same 403/`Skipping` handling as the loop (a single URL, so a 403 raises after cleanup of leftovers).

When `watch_url` is empty, keep search + `rank_youtube_sources`. Track `tried_ids: set[str]` for every candidate whose watch URL was attempted (including 403 and match-filter skip). Before every `raise` and after the candidate loop fails, if `picker_out is not None`:

```python
picker_out.clear()
picker_out.extend(collect_picker_sources(entries, tried_ids))
```

If there are no ranked candidates, `tried_ids` is empty and `entries` is the raw search list, then raise `DownloadError("No matching audio source found")` after filling `picker_out`.

Existing `test_youtube_download_retries_next_result_after_403` must still pass: first Topic id 403s, second VEVO id succeeds, no `picker_out` required.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_download_watch_url_skips_search_and_uses_that_url tests/test_app.py::test_auto_download_failure_fills_picker_excluding_tried_ids tests/test_app.py::test_youtube_download_retries_next_result_after_403 tests/test_app.py::test_source_limit_is_passed_to_ytdlp_and_equality_is_allowed`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Skip search for a chosen watch URL and record leftover picker hits."
```

---

### Task 3: Persist picker state on job failure

**Files:**
- Modify: `app.py` (`Job` around line 66, `process_song` around line 1300, `retain_artifact` success path already discards `failed`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `download_song_from_youtube(..., picker_out=, watch_url=)`, `collect_picker_sources`
- Produces: `Job.source_choices: dict[int, list[dict[str, Any]]]`, `Job.forced_sources: dict[int, str]`. `process_song` pops `forced_sources[index]` for `watch_url`, replaces `source_choices[index]` on auto start, stores leftovers and `can_choose_source` on fail, clears both on success. Fail messages: `"Download failed. You can retry this track or choose a source."` when leftovers exist, else `"Download failed. No alternate sources found."`

- [ ] **Step 1: Write the failing test**

```python
def test_process_song_stores_picker_sources_and_can_choose_flag(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def fail_download(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        out = kwargs.get("picker_out")
        if out is not None:
            out.clear()
            out.extend([{
                "id": "labellabel1",
                "title": "Halo Official Audio",
                "channel": "Label Records",
                "duration": 201,
            }])
        raise application.DownloadError("No matching audio source found")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_download)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert 0 in job.failed
    assert job.source_choices[0][0]["id"] == "labellabel1"
    assert job.statuses[0]["can_choose_source"] is True
    assert "choose a source" in job.statuses[0]["message"]


def test_process_song_forced_watch_url_403_drops_that_picker_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201},
        {"id": "lyriclyric1", "title": "Halo Lyric Video", "channel": "Starling", "duration": 202},
    ]
    job.forced_sources[0] = "labellabel1"
    captured: dict[str, str] = {}

    def fail_forced(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        captured["watch_url"] = kwargs.get("watch_url") or ""
        raise application.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_forced)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert captured["watch_url"] == "https://www.youtube.com/watch?v=labellabel1"
    assert [item["id"] for item in job.source_choices[0]] == ["lyriclyric1"]
    assert job.statuses[0]["can_choose_source"] is True
    assert 0 not in job.forced_sources
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_process_song_stores_picker_sources_and_can_choose_flag tests/test_app.py::test_process_song_forced_watch_url_403_drops_that_picker_id`

Expected: FAIL (`Job` has no `source_choices` or fail payload lacks `can_choose_source`)

- [ ] **Step 3: Write minimal implementation**

Add to `Job`:

```python
source_choices: dict[int, list[dict[str, Any]]] = field(default_factory=dict)
forced_sources: dict[int, str] = field(default_factory=dict)
```

In `process_song`, before calling `download_song_from_youtube`:

```python
with job.lock:
    forced_id = job.forced_sources.pop(index, "")
    if not forced_id:
        job.source_choices.pop(index, None)
watch = f"https://www.youtube.com/watch?v={forced_id}" if youtube_video_id(forced_id) else ""
picker_out: list[dict[str, Any]] = []
download_song_from_youtube(
    f"{song['Artist']} {song['Song']}",
    output_base,
    ffmpeg,
    on_progress,
    int(app.config["MAX_SOURCE_BYTES"]),
    artist=song["Artist"],
    title=song["Song"],
    watch_url=watch,
    picker_out=picker_out,
)
```

On success, after `retain_artifact`:

```python
with job.lock:
    job.source_choices.pop(index, None)
    job.forced_sources.pop(index, None)
```

Do not add `can_choose_source` to the success payload.

In the `except` block, after `job.failed.add(index)`:

```python
with job.lock:
    job.failed.add(index)
    if forced_id:
        remaining = [
            item for item in job.source_choices.get(index, [])
            if item.get("id") != forced_id
        ]
        if remaining:
            job.source_choices[index] = remaining
        else:
            job.source_choices.pop(index, None)
    elif picker_out:
        job.source_choices[index] = list(picker_out)
    else:
        job.source_choices.pop(index, None)
    can_choose = bool(job.source_choices.get(index))
message = (
    "Download failed. You can retry this track or choose a source."
    if can_choose
    else "Download failed. No alternate sources found."
)
publish("failed", message, can_choose_source=can_choose)
```

`forced_id` must be assigned before the `try` so the `except` can see it (empty string if none). Existing tests that look for `"Download failed. You can retry this track."` must be updated to the new with-picker or no-alternates string only if they fail a download; grep `test_app.py` for that exact sentence and update those assertions.

A new automatic attempt (no `forced_id`) clears `source_choices[index]` at start, so **Retry failed** replaces the list after the next search.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_process_song_stores_picker_sources_and_can_choose_flag tests/test_app.py::test_process_song_forced_watch_url_403_drops_that_picker_id tests/test_app.py -k "failed or retry or process_song"`

Expected: PASS (fix any stale fail-message assertions)

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Store leftover sources on failed tracks for later choice."
```

---

### Task 4: Source list, choose-source, and thumbnail routes

**Files:**
- Modify: `app.py` (`create_app` routes near `/download` around line 1708)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `owned_job`, `mutation_job`, `queue_indices`, `youtube_video_id`, `Job.source_choices`, `Job.forced_sources`, `_read_limited_response`
- Produces: `GET /tracks/<index>/sources`, `POST /choose-source`, `GET /tracks/<index>/source-thumbs/<video_id>`, `fetch_source_thumbnail(video_id: str, max_bytes: int) -> bytes | None`, `SOURCE_THUMB_MAX_BYTES = 200_000`, `YOUTUBE_THUMB_HOST = "i.ytimg.com"`

- [ ] **Step 1: Write the failing tests**

```python
def test_choose_source_routes_require_failed_stored_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    token = csrf_for(app, client)
    missing = client.get("/tracks/0/sources")
    assert missing.status_code == 409
    job.failed.add(0)
    job.statuses[0] = {"job_id": job.job_id, "index": 0, "status": "failed", "message": "failed"}
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201},
    ]
    listed = client.get("/tracks/0/sources")
    assert listed.status_code == 200
    assert listed.json["sources"][0]["id"] == "labellabel1"
    forged = client.post(
        "/choose-source",
        json={"index": 0, "video_id": "forgedforged"},
        headers={"X-CSRFToken": token},
    )
    assert forged.status_code == 409
    started: list[int] = []

    def fake_queue(current, indices):
        started.extend(indices)
        current.forced_sources[indices[0]] = current.forced_sources.get(indices[0], "")
        return indices

    monkeypatch.setattr(application, "queue_indices", fake_queue)
    # Patch the nested queue_indices used by the Flask app by going through the live function:
    monkeypatch.setattr("app.queue_indices", fake_queue)
```

Do **not** patch a module-level `queue_indices` that does not exist at import time. `queue_indices` is nested in `create_app`. Drive the real queue with a mocked `download_song_from_youtube` instead:

Replace the `fake_queue` approach with this complete test:

```python
def test_choose_source_routes_require_failed_stored_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    token = csrf_for(app, client)
    assert client.get("/tracks/0/sources").status_code == 409
    job.failed.add(0)
    job.statuses[0] = {
        "job_id": job.job_id,
        "index": 0,
        "status": "failed",
        "message": "failed",
        "can_choose_source": True,
    }
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201},
    ]
    listed = client.get("/tracks/0/sources")
    assert listed.status_code == 200
    assert listed.json["sources"][0]["id"] == "labellabel1"
    no_csrf = client.post("/choose-source", json={"index": 0, "video_id": "labellabel1"})
    assert no_csrf.status_code == 400
    forged = client.post(
        "/choose-source",
        json={"index": 0, "video_id": "forgedforged"},
        headers={"X-CSRFToken": token},
    )
    assert forged.status_code == 409
    captured: dict[str, str] = {}

    def fake_download(_query, output_base, _ffmpeg, _progress, _max_source, **kwargs):
        captured["watch_url"] = kwargs.get("watch_url") or ""
        output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "download_song_from_youtube", fake_download)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(app.extensions["socketio_instance"], "emit", lambda *args, **kwargs: None)
    accepted = client.post(
        "/choose-source",
        json={"index": 0, "video_id": "labellabel1"},
        headers={"X-CSRFToken": token},
    )
    assert accepted.status_code == 202
    if job.reserved_indices or job.pending_indices:
        application.process_song(app, app.extensions["socketio_instance"], job.job_id, 0, dict(job.songs[0]), job.reservation_sizes.get(0) or app.config["TASK_BYTE_RESERVATION"])
    assert captured.get("watch_url") == "https://www.youtube.com/watch?v=labellabel1"


def test_source_thumbnail_allows_only_stored_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {"status": "failed", "index": 0, "job_id": job.job_id, "message": "failed"}
    job.source_choices[0] = [{"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201}]
    jpeg = b"\xff\xd8" + b"thumb" + b"\xff\xd9"

    class FakeResponse:
        headers = {"Content-Type": "image/jpeg", "Content-Length": str(len(jpeg))}
        content = jpeg

        def raise_for_status(self):
            return None

        def iter_content(self, _size):
            yield jpeg

        def close(self):
            return None

    def fake_get(url, **kwargs):
        captured["url"] = url
        captured["allow_redirects"] = kwargs.get("allow_redirects")
        return FakeResponse()

    captured: dict[str, Any] = {}
    monkeypatch.setattr(application.requests, "get", fake_get)
    missing = client.get("/tracks/0/source-thumbs/forgedforged")
    assert missing.status_code == 404
    ok = client.get("/tracks/0/source-thumbs/labellabel1")
    assert ok.status_code == 200
    assert ok.data.startswith(b"\xff\xd8")
    assert captured["url"] == "https://i.ytimg.com/vi/labellabel1/hqdefault.jpg"
    assert captured["allow_redirects"] is False
```

Move `captured: dict[str, Any] = {}` above `fake_get` in the thumbnail test (the block above declares it after `fake_get` by mistake). The implementer must declare `captured` first.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_choose_source_routes_require_failed_stored_id tests/test_app.py::test_source_thumbnail_allows_only_stored_id`

Expected: FAIL with Flask 404 for unknown routes

- [ ] **Step 3: Write minimal implementation**

Module constants:

```python
SOURCE_THUMB_MAX_BYTES = 200_000
```

```python
def fetch_source_thumbnail(video_id: str, max_bytes: int) -> bytes | None:
    if youtube_video_id(video_id) is None:
        return None
    try:
        image = requests.get(
            f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg",
            timeout=(3.05, 8),
            stream=True,
            allow_redirects=False,
        )
        if image.status_code != 200:
            return None
        payload = _read_limited_response(image, max_bytes)
        if payload.startswith(b"\xff\xd8"):
            return payload
        return None
    except (requests.RequestException, ValueError):
        return None
```

Inside `create_app`, after `queue_indices`:

```python
def failed_index(job: Job, index: int) -> bool:
    with job.lock:
        if index < 0 or index >= len(job.songs):
            return False
        if index in job.reserved_indices or index in job.pending_indices:
            return False
        return job.statuses.get(index, {}).get("status") == "failed"

@flask_app.route("/tracks/<int:index>/sources", methods=["GET"])
@limiter.limit("60 per minute")
def track_sources(index: int) -> Any:
    job = owned_job()
    if job is None:
        return jsonify(error="Current job is unavailable; refresh the page"), 403
    if not failed_index(job, index):
        return jsonify(error="Alternate sources are available only for a failed track"), 409
    with job.lock:
        sources = list(job.source_choices.get(index) or [])
    return jsonify(sources=sources)

@flask_app.route("/choose-source", methods=["POST"])
@limiter.limit("20 per minute")
def choose_source() -> Any:
    job, error_response = mutation_job()
    if error_response:
        return error_response
    assert job is not None
    payload = request.get_json(silent=True) or {}
    try:
        index = int(payload.get("index"))
    except (TypeError, ValueError):
        return jsonify(error="Selection is invalid"), 400
    video_id = youtube_video_id(str(payload.get("video_id") or ""))
    if video_id is None:
        return jsonify(error="That source is not available"), 409
    if not failed_index(job, index):
        return jsonify(error="Choose a source only for a failed track"), 409
    with job.lock:
        allowed = {item.get("id") for item in job.source_choices.get(index) or []}
        if video_id not in allowed:
            return jsonify(error="That source is not available"), 409
        job.forced_sources[index] = video_id
    try:
        started = queue_indices(job, [index])
    except (JobAdmissionError, JobUnavailableError) as exc:
        with job.lock:
            if job.forced_sources.get(index) == video_id:
                job.forced_sources.pop(index, None)
        return jsonify(error=str(exc)), 409
    return jsonify(job_id=job.job_id, started=started), 202

@flask_app.route("/tracks/<int:index>/source-thumbs/<video_id>", methods=["GET"])
@limiter.limit("60 per minute")
def track_source_thumb(index: int, video_id: str) -> Any:
    job = owned_job()
    if job is None:
        return jsonify(error="File not found"), 404
    bound = youtube_video_id(video_id)
    with job.lock:
        allowed = {item.get("id") for item in job.source_choices.get(index) or []}
        if not failed_index(job, index) or bound is None or bound not in allowed:
            return jsonify(error="File not found"), 404
    image = fetch_source_thumbnail(bound, min(SOURCE_THUMB_MAX_BYTES, int(flask_app.config["ARTWORK_MAX_BYTES"])))
    if not image:
        return jsonify(error="File not found"), 404
    return flask_app.response_class(image, mimetype="image/jpeg")
```

`failed_index` takes the lock; `track_source_thumb` must not call it while already holding `job.lock`. Either inline the status checks in the thumb route without nested lock, or make `failed_index` assume the caller holds the lock. Prefer: drop the inner lock from `failed_index` and document that callers hold `job.lock` **or** call it without nested locking by copying status under one `with job.lock` in each route.

Use this lock-safe version instead of nesting:

```python
def failed_track_locked(job: Job, index: int) -> bool:
    if index < 0 or index >= len(job.songs):
        return False
    if index in job.reserved_indices or index in job.pending_indices:
        return False
    return job.statuses.get(index, {}).get("status") == "failed"
```

Each route uses `with job.lock:` once.

If `start_background_task` actually runs `process_song` in tests, `captured["watch_url"]` may already be set and the manual `process_song` call is unnecessary. Assert after the POST; only call `process_song` if `captured` is still empty and the index is reserved.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_choose_source_routes_require_failed_stored_id tests/test_app.py::test_source_thumbnail_allows_only_stored_id`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Add failed-track source choice and same-origin thumbnail routes."
```

---

### Task 5: Dialog UI

**Files:**
- Modify: `templates/index.html` (action cell around line 131; before `</main>`)
- Modify: `static/app.js` (`setTrackState` around line 101; new dialog handlers)
- Modify: `static/style.css` (after `.download-link`)
- Test: `tests/test_app.py` (`test_render_includes_accessibility_and_local_ui_contract` plus a failed-row render test)

**Interfaces:**
- Consumes: `can_choose_source` on `job.statuses[index]`, GET `/tracks/<index>/sources`, POST `/choose-source`, GET `/tracks/<index>/source-thumbs/<id>`
- Produces: `#source-dialog`, `.choose-source` buttons, `setTrackState` toggling the button from `can_choose_source`

- [ ] **Step 1: Write the failing tests**

Extend `test_render_includes_accessibility_and_local_ui_contract` with:

```python
assert b'id="source-dialog"' in response.data
assert b"Choose source" in response.data
```

Add:

```python
def test_failed_row_renders_choose_source_when_flag_set(app, client):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {
        "job_id": job.job_id,
        "index": 0,
        "status": "failed",
        "message": "Download failed. You can retry this track or choose a source.",
        "can_choose_source": True,
    }
    page = client.get("/")
    assert page.status_code == 200
    assert b'class="choose-source"' in page.data
    assert b'id="source-dialog"' in page.data
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_failed_row_renders_choose_source_when_flag_set`

Expected: FAIL (`id="source-dialog"` missing)

- [ ] **Step 3: Write minimal implementation**

In `templates/index.html` action cell, after the download link:

```html
<button class="button button-quiet choose-source" type="button" data-index="{{ index }}" {% if not state.get('can_choose_source') %}hidden{% endif %}>Choose source</button>
```

Before `</main>`:

```html
<dialog id="source-dialog" aria-labelledby="source-dialog-title">
  <form method="dialog" class="source-dialog-chrome">
    <h2 id="source-dialog-title">Choose a source</h2>
    <p id="source-dialog-meta"></p>
    <div id="source-dialog-cards" class="source-cards"></div>
    <button class="button button-quiet" id="source-dialog-close" value="cancel">Close</button>
  </form>
</dialog>
```

In `static/app.js`, inside `setTrackState`, after the download-link block:

```javascript
    const choose = row.querySelector(".choose-source");
    if (choose) {
      const show = data.status === "failed" && data.can_choose_source === true;
      choose.hidden = !show;
    }
```

Add dialog wiring after the retry handler (use `mutate` / `csrfToken` already defined):

```javascript
  const sourceDialog = document.getElementById("source-dialog");
  const sourceMeta = document.getElementById("source-dialog-meta");
  const sourceCards = document.getElementById("source-dialog-cards");
  let sourceOpener = null;

  const formatDuration = (seconds) => {
    if (!Number.isFinite(Number(seconds))) return "";
    const total = Math.max(0, Math.floor(Number(seconds)));
    const minutes = Math.floor(total / 60);
    const remain = String(total % 60).padStart(2, "0");
    return `${minutes}:${remain}`;
  };

  const closeSourceDialog = () => {
    sourceDialog?.close();
    sourceOpener?.focus();
    sourceOpener = null;
  };

  const openSourceDialog = async (button) => {
    const row = button.closest("tr");
    const index = Number(button.dataset.index);
    if (!row || row.dataset.state !== "failed" || button.hidden) return;
    sourceOpener = button;
    const title = row.querySelector('[data-label="Track"] strong')?.textContent || "this track";
    const artist = row.querySelector('[data-label="Artist"]')?.textContent || "";
    if (sourceMeta) sourceMeta.textContent = `${title} · ${artist}`;
    if (sourceCards) sourceCards.replaceChildren();
    sourceDialog?.showModal();
    document.getElementById("source-dialog-close")?.focus();
    const data = await parseResponse(await fetch(`/tracks/${index}/sources`, {
      credentials: "same-origin",
      headers: { Accept: "application/json" },
    }));
    (data.sources || []).forEach((source) => {
      const card = document.createElement("article");
      card.className = "source-card";
      const image = document.createElement("img");
      image.alt = "";
      image.src = `/tracks/${index}/source-thumbs/${encodeURIComponent(source.id)}`;
      image.addEventListener("error", () => image.remove());
      const heading = document.createElement("h3");
      heading.textContent = source.title || "Untitled";
      const channel = document.createElement("p");
      channel.textContent = [source.channel, formatDuration(source.duration)].filter(Boolean).join(" · ");
      const use = document.createElement("button");
      use.type = "button";
      use.className = "button button-primary";
      use.textContent = "Use this source";
      use.addEventListener("click", () => withBusyButton(use, "Starting…", async () => {
        sourceCards?.querySelectorAll("button").forEach((item) => { item.disabled = true; });
        setTrackState({ job_id: jobId, index, status: "queued", message: "Queued" });
        closeSourceDialog();
        const result = await mutate("/choose-source", {
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ index, video_id: source.id }),
        });
        announce(`${result.started.length} track${result.started.length === 1 ? "" : "s"} queued.`, "success");
      }));
      card.append(image, heading, channel, use);
      sourceCards?.append(card);
    });
  };

  document.querySelectorAll(".choose-source").forEach((button) => {
    button.addEventListener("click", () => {
      openSourceDialog(button).catch((error) => announce(error.message, "error"));
    });
  });
  sourceDialog?.addEventListener("click", (event) => {
    if (event.target === sourceDialog) closeSourceDialog();
  });
```

Native `<dialog>` already closes on Escape. `method="dialog"` Close button closes without downloading.

CSS using existing tokens (`--panel-2`, `--line`, `--ink`, `--muted`, `--acid`):

```css
.choose-source { margin-left: 8px; }
.source-dialog-chrome { min-width: min(520px, 100%); padding: 20px; }
.source-cards { display: grid; gap: 12px; margin: 16px 0; }
.source-card { display: grid; grid-template-columns: 96px 1fr; gap: 8px 12px; padding: 12px; border: 1px solid var(--line); border-radius: 12px; background: var(--panel-2); }
.source-card img { width: 96px; height: 72px; object-fit: cover; border-radius: 8px; background: #0d1011; }
.source-card h3 { margin: 0; color: var(--ink); font-size: .92rem; }
.source-card p { margin: 0; color: var(--muted); font-size: .78rem; }
.source-card .button { grid-column: 2; justify-self: start; }
#source-dialog { border: 1px solid var(--line); border-radius: 16px; background: #121516; color: var(--ink); }
#source-dialog::backdrop { background: rgb(0 0 0 / 55%); }
```

If `openSourceDialog` fetch fails, close the dialog and toast the error.

- [ ] **Step 4: Run tests and syntax check**

Run:

```text
python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_failed_row_renders_choose_source_when_flag_set
node --check static/app.js
```

Expected: PASS; `node --check` exits 0

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/app.js static/style.css tests/test_app.py
git commit -m "Add a failed-track dialog for choosing a YouTube source."
```

---

### Task 6: README and full verification

**Files:**
- Modify: `README.md` (source-processing paragraph around line 41)

**Interfaces:**
- Consumes: behavior from Tasks 1–5
- Produces: one README sentence; green full suite

- [ ] **Step 1: Update README**

Append to the source-processing paragraph (do not rewrite unrelated sentences):

```text
If automatic download fails, the failed row can offer up to three leftover YouTube hits to choose from; the pick still goes through the same job reservation and size limits.
```

- [ ] **Step 2: Run full verification**

```text
python -m py_compile app.py
node --check static/app.js
python -m pytest -q
```

Expected: compile ok;  all existing tests plus new tests pass (count will be previous 72 plus the tests added in this plan).

- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document failed-track source choice in the README."
```

---

## Self-review

**Spec coverage**

| Spec requirement | Task |
|---|---|
| Failure-only **Choose source** button and dialog (no embed) | 5 |
| Raw-search leftovers, max 3, drop tried/short/long/movie/clean/variant | 1 |
| Memory-only `source_choices`; replace on new auto attempt; drop chosen id on 403 | 3 |
| GET sources / POST choose-source / CSRF / forced watch URL | 2, 4 |
| Same-origin thumbnail, bound id, no arbitrary URL | 4 |
| Fail payload `can_choose_source` and messages | 3 |
| `watch_url` skips search; auto 403 fallback among approved hits unchanged | 2 |
| Retry failed still auto-searches | 3 (clears list at auto start) |
| README sentence | 6 |
| Mocked tests, no live YouTube | 1–5 |

**Placeholders:** none remaining. Task 4 lock nesting is specified as a single `with job.lock` plus `failed_track_locked`.

**Names:** `collect_picker_sources`, `youtube_video_id`, `source_choices`, `forced_sources`, `picker_out`, `watch_url`, `fetch_source_thumbnail`, `can_choose_source` are used consistently across tasks.
