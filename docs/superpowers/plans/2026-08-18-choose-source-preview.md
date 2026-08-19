# Choose Source 30-Second Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On a failed track’s Choose source dialog, play a ~30-second same-origin MP3 preview of a leftover YouTube hit without saving the track or embedding YouTube.

**Architecture:** `GET /tracks/<index>/source-previews/<video_id>` builds or serves `preview-<id>.mp3` in the job directory. yt-dlp downloads that stored watch URL with a 0–30s range, FFmpeg extracts MP3, and the dialog’s shared `<audio>` plays it. Cache and a per-job `preview_lock` prevent stacked downloads. The clip is not retained, not Saved, and not written to the library.

**Tech Stack:** Flask, yt-dlp (mocked in tests), FFmpeg path from existing resolver, vanilla JS, pytest.

## Global Constraints

- Picker is failure-only; **Start selected**, **Retry failed**, **Use this source**, and **Load more** keep their current meaning.
- Accept only an 11-character YouTube id (`[A-Za-z0-9_-]{11}`) already in that track’s stored leftover list; never a pasted URL.
- Clip is at most **30** seconds from the start. Output must not exceed `PREVIEW_MAX_BYTES = 5_000_000`.
- Do not call `save_mp3_to_library`, `retain_artifact`, `tag_mp3_file` (library tags), or add the path to `job.files`.
- Do not widen CSP `img-src` or add YouTube `frame-src`. Add `media-src 'self'` only.
- Do not hit live YouTube or iTunes in tests; mock yt-dlp.
- One clip build in flight per job (`Job.preview_lock`). A second GET waits on that lock, then cache or 404.
- Do not 409 previews when the library folder is unusable.
- Existing YouTube `player_client` list stays `["web_embedded", "default", "-android_vr", "-ios", "-android_sdkless"]`.

## File map

- `app.py` — `PREVIEW_SECONDS`, `PREVIEW_MAX_BYTES`, `preview_clip_path`, `build_source_preview`, `Job.preview_lock`, CSP, GET route.
- `templates/index.html` — hidden shared `<audio id="source-dialog-audio">`.
- `static/app.js` — Play/Pause on each card, one player, loading/unavailable.
- `static/style.css` — `.source-card-actions` so Play and Use this source sit together.
- `tests/test_app.py` — helper, route, overlap, cache, CSP/UI contract.

Do not split `app.py`. Do not add a POST for preview.

---

### Task 1: Preview clip helper and job lock

**Files:**
- Modify: `app.py` (`Job` dataclass near `lock:`; constants near `SOURCE_THUMB_MAX_BYTES`; helpers after `fetch_source_thumbnail`)
- Test: `tests/test_app.py` (after `test_source_thumbnail_allows_only_stored_id`)

**Interfaces:**
- Consumes: `youtube_video_id`, `YoutubeDL`, `DownloadError`, `resolve_js_runtime`, `undesired_youtube_source`, existing `extractor_args` player_client list
- Produces: `PREVIEW_SECONDS = 30`, `PREVIEW_MAX_BYTES = 5_000_000`, `Job.preview_lock: threading.Lock`, `preview_clip_path(job_directory: Path, video_id: str) -> Path`, `build_source_preview(job_directory: Path, video_id: str, ffmpeg_path: str, max_source_bytes: int) -> Path | None`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_app.py`:

```python
def test_preview_clip_path_uses_job_dir_and_video_id(tmp_path):
    path = application.preview_clip_path(tmp_path / "job", "labellabel1")
    assert path == tmp_path / "job" / "preview-labellabel1.mp3"
    with pytest.raises(ValueError):
        application.preview_clip_path(tmp_path / "job", "bad")


def test_build_source_preview_writes_bounded_mp3_without_library_or_retain(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()
    library = tmp_path / "library"
    library.mkdir()
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
            Path(captured["outtmpl"].replace(".%(ext)s", ".mp3")).write_bytes(b"ID3preview")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    monkeypatch.setattr(application, "save_mp3_to_library", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("preview must not save to library")))
    result = application.build_source_preview(job_dir, "labellabel1", "ffmpeg", 100)
    assert result == job_dir / "preview-labellabel1.mp3"
    assert result.read_bytes() == b"ID3preview"
    assert captured["queries"] == ["https://www.youtube.com/watch?v=labellabel1"]
    assert captured["download_ranges"](None, None) == [{"start_time": 0, "end_time": 30}]
    assert captured["extractor_args"]["youtube"]["player_client"] == [
        "web_embedded",
        "default",
        "-android_vr",
        "-ios",
        "-android_sdkless",
    ]
    assert captured["noplaylist"] is True
    assert captured["writethumbnail"] is False
    assert list(library.iterdir()) == []
    assert application.PREVIEW_SECONDS == 30
    assert application.PREVIEW_MAX_BYTES == 5_000_000


def test_build_source_preview_returns_none_on_403_or_oversize(tmp_path, monkeypatch):
    job_dir = tmp_path / "job"
    job_dir.mkdir()

    class FailYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _queries):
            raise application.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")

    monkeypatch.setattr(application, "YoutubeDL", FailYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    assert application.build_source_preview(job_dir, "labellabel1", "ffmpeg", 100) is None
    assert not (job_dir / "preview-labellabel1.mp3").exists()

    class FatYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _queries):
            path = Path(self.options["outtmpl"].replace(".%(ext)s", ".mp3"))
            path.write_bytes(b"x" * (application.PREVIEW_MAX_BYTES + 1))

    monkeypatch.setattr(application, "YoutubeDL", FatYDL)
    assert application.build_source_preview(job_dir, "labellabel1", "ffmpeg", 100) is None
    assert not (job_dir / "preview-labellabel1.mp3").exists()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_preview_clip_path_uses_job_dir_and_video_id tests/test_app.py::test_build_source_preview_writes_bounded_mp3_without_library_or_retain tests/test_app.py::test_build_source_preview_returns_none_on_403_or_oversize`

Expected: FAIL (`preview_clip_path` is not defined)

- [ ] **Step 3: Implement helpers**

On `Job`, after `lock: threading.RLock = field(default_factory=threading.RLock, repr=False)` add:

```python
    preview_lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
```

Near `SOURCE_THUMB_MAX_BYTES = 200_000` add:

```python
PREVIEW_SECONDS = 30
PREVIEW_MAX_BYTES = 5_000_000
```

After `fetch_source_thumbnail`:

```python
def preview_clip_path(job_directory: Path, video_id: str) -> Path:
    bound = youtube_video_id(video_id)
    if bound is None:
        raise ValueError("Invalid YouTube video id")
    return Path(job_directory) / f"preview-{bound}.mp3"


def build_source_preview(
    job_directory: Path,
    video_id: str,
    ffmpeg_path: str,
    max_source_bytes: int,
) -> Path | None:
    bound = youtube_video_id(video_id)
    if bound is None:
        return None
    output_base = Path(job_directory) / f"preview-{bound}"
    dest = preview_clip_path(job_directory, bound)
    runtime_name, runtime_path = resolve_js_runtime()
    options = {
        "quiet": True,
        "retries": 3,
        "socket_timeout": 30,
        "js_runtimes": {runtime_name: {"path": runtime_path}},
        "extractor_args": {
            "youtube": {
                "player_client": ["web_embedded", "default", "-android_vr", "-ios", "-android_sdkless"],
            }
        },
        "format": "bestaudio/best",
        "outtmpl": f"{output_base}.%(ext)s",
        "ffmpeg_location": ffmpeg_path,
        "max_filesize": max_source_bytes,
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "match_filter": undesired_youtube_source,
        "writethumbnail": False,
        "noplaylist": True,
        "download_ranges": lambda _info, _ydl: [{"start_time": 0, "end_time": PREVIEW_SECONDS}],
    }

    def remove_leftovers() -> None:
        for leftover in output_base.parent.glob(f"{output_base.name}.*"):
            try:
                leftover.unlink(missing_ok=True)
            except OSError:
                LOGGER.warning("Could not remove preview leftover %s", leftover.name)

    try:
        with YoutubeDL(options) as downloader:
            downloader.download([f"https://www.youtube.com/watch?v={bound}"])
    except DownloadError:
        remove_leftovers()
        return None
    if not dest.is_file():
        produced = output_base.with_suffix(".mp3")
        if produced.is_file() and produced != dest:
            produced.replace(dest)
    if not dest.is_file():
        remove_leftovers()
        return None
    if dest.stat().st_size > PREVIEW_MAX_BYTES:
        dest.unlink(missing_ok=True)
        remove_leftovers()
        return None
    return dest
```

`outtmpl` is `preview-<id>.%(ext)s`, so FFmpeg extract already writes `preview-<id>.mp3` (`dest`). Keep the `produced.replace` branch only if tests need it; if `dest.is_file()` after download, skip rename.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_preview_clip_path_uses_job_dir_and_video_id tests/test_app.py::test_build_source_preview_writes_bounded_mp3_without_library_or_retain tests/test_app.py::test_build_source_preview_returns_none_on_403_or_oversize`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Add a 30-second leftover source preview clip helper."
```

---

### Task 2: Preview GET route and CSP

**Files:**
- Modify: `app.py` (`security_headers` CSP string; add route after `track_source_thumb`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `preview_clip_path`, `build_source_preview`, `Job.preview_lock`, `owned_job`, `failed_track_locked`, `youtube_video_id`, `resolve_ffmpeg`
- Produces: `GET /tracks/<index>/source-previews/<video_id>` → 200 `audio/mpeg` or 404; CSP includes `media-src 'self'`

- [ ] **Step 1: Write the failing tests**

In `test_render_includes_accessibility_and_local_ui_contract`, after the status 200 assertion, add:

```python
    assert "media-src 'self'" in response.headers.get("Content-Security-Policy", "")
    assert "youtube.com" not in response.headers.get("Content-Security-Policy", "")
```

Add after `test_source_thumbnail_allows_only_stored_id`:

```python
def test_source_preview_route_serves_cached_clip_for_stored_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {"status": "failed", "index": 0, "job_id": job.job_id, "message": "failed", "can_choose_source": True}
    job.source_choices[0] = [{"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201}]
    builds: list[str] = []

    def fake_build(job_directory, video_id, ffmpeg_path, max_source_bytes):
        builds.append(video_id)
        path = application.preview_clip_path(job_directory, video_id)
        path.write_bytes(b"ID3clip")
        return path

    monkeypatch.setattr(application, "build_source_preview", fake_build)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    missing = client.get("/tracks/0/source-previews/unboundxyz1")
    assert missing.status_code == 404
    queued = dict(job.statuses[0])
    job.statuses[0]["status"] = "queued"
    assert client.get("/tracks/0/source-previews/labellabel1").status_code == 404
    job.statuses[0] = queued
    ok = client.get("/tracks/0/source-previews/labellabel1")
    assert ok.status_code == 200
    assert ok.mimetype == "audio/mpeg"
    assert ok.data == b"ID3clip"
    assert job.files == {}
    assert 0 not in job.files
    cached = client.get("/tracks/0/source-previews/labellabel1")
    assert cached.status_code == 200
    assert builds == ["labellabel1"]
    assert job.statuses[0]["can_choose_source"] is True


def test_source_preview_403_is_404_and_leaves_picker(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {"status": "failed", "index": 0, "job_id": job.job_id, "message": "failed", "can_choose_source": True}
    job.source_choices[0] = [{"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201}]
    monkeypatch.setattr(application, "build_source_preview", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    assert client.get("/tracks/0/source-previews/labellabel1").status_code == 404
    assert job.source_choices[0][0]["id"] == "labellabel1"
    assert job.statuses[0]["can_choose_source"] is True
    assert job.statuses[0]["status"] == "failed"


def test_source_preview_builds_do_not_overlap_on_one_job(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {"status": "failed", "index": 0, "job_id": job.job_id, "message": "failed", "can_choose_source": True}
    job.source_choices[0] = [
        {"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201},
        {"id": "lyriclyric1", "title": "Halo lyrics", "channel": "Starling", "duration": 202},
    ]
    active = 0
    max_active = 0
    gate = threading.Lock()
    started = threading.Barrier(2)

    def fake_build(job_directory, video_id, ffmpeg_path, max_source_bytes):
        nonlocal active, max_active
        with gate:
            active += 1
            max_active = max(max_active, active)
        started.wait(2)
        path = application.preview_clip_path(job_directory, video_id)
        path.write_bytes(video_id.encode("ascii"))
        with gate:
            active -= 1
        return path

    monkeypatch.setattr(application, "build_source_preview", fake_build)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    errors: list[BaseException] = []

    def pull(video_id: str) -> None:
        try:
            response = client.get(f"/tracks/0/source-previews/{video_id}")
            assert response.status_code == 200
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=pull, args=("labellabel1",))
    second = threading.Thread(target=pull, args=("lyriclyric1",))
    first.start()
    second.start()
    first.join()
    second.join()
    assert errors == []
    assert max_active == 1
```

If the Flask test client is not thread-safe, run both GETs through `app.test_client()` clones that share the same session cookie, or call the view with `preview_lock` by invoking `build` under the route’s lock in a thinner test: two threads calling a small wrapper that uses `job.preview_lock` around `fake_build`. Prefer hitting the real route; copy the session cookie onto two clients if needed:

```python
    cookie = client.get_cookie("session")
```

Use one `client` and `threading` only if the first overlap test flakes; then assert `max_active == 1` by wrapping `build_source_preview` as above. Flask’s test client often serializes; if `max_active` stays 1 because the client is single-threaded, replace the test with a direct lock test:

```python
def test_preview_lock_prevents_nested_builds(app, client, monkeypatch):
    ...
    def under_lock(video_id: str) -> None:
        with job.preview_lock:
            fake_build(job.directory, video_id, "ffmpeg", 100)

    # still start two threads both doing with job.preview_lock: fake_build
```

The route **must** take `job.preview_lock` around cache-check + build so that test can target the route. If the test client cannot overlap, keep the two-thread test on `job.preview_lock` + `build_source_preview` and a comment in the route that the lock is required.

Simplest passing overlap test that does not depend on Flask client threads:

```python
def test_job_preview_lock_serializes_builders():
    job = application.Job(job_id="j", directory=Path("."))
    active = 0
    max_active = 0
    gate = threading.Lock()

    def work() -> None:
        nonlocal active, max_active
        with job.preview_lock:
            with gate:
                active += 1
                max_active = max(max_active, active)
            threading.Event().wait(0.05)
            with gate:
                active -= 1

    threads = [threading.Thread(target=work) for _ in range(2)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert max_active == 1
```

Use **this** overlap test in Task 2 (Job is importable). The route still uses `with job.preview_lock`.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_source_preview_route_serves_cached_clip_for_stored_id tests/test_app.py::test_source_preview_403_is_404_and_leaves_picker tests/test_app.py::test_job_preview_lock_serializes_builders`

Expected: FAIL (no `/source-previews/` route; CSP missing `media-src`)

`test_job_preview_lock_serializes_builders` may PASS as soon as Task 1 added `preview_lock`. That is acceptable if Task 1 already shipped the lock.

- [ ] **Step 3: CSP and route**

Change the CSP string to:

```python
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; media-src 'self'; connect-src 'self' ws: wss:",
```

After `track_source_thumb`, add:

```python
    @flask_app.route("/tracks/<int:index>/source-previews/<video_id>", methods=["GET"])
    @limiter.limit("60 per minute")
    def track_source_preview(index: int, video_id: str) -> Any:
        job = owned_job()
        if job is None:
            return jsonify(error="File not found"), 404
        bound = youtube_video_id(video_id)
        with job.lock:
            allowed = {item.get("id") for item in job.source_choices.get(index) or []}
            if not failed_track_locked(job, index) or bound is None or bound not in allowed:
                return jsonify(error="File not found"), 404
        with job.preview_lock:
            cached = preview_clip_path(job.directory, bound)
            if cached.is_file() and 0 < cached.stat().st_size <= PREVIEW_MAX_BYTES:
                payload = cached.read_bytes()
            else:
                built = build_source_preview(
                    job.directory,
                    bound,
                    resolve_ffmpeg(flask_app.config.get("FFMPEG_PATH")),
                    int(flask_app.config["MAX_SOURCE_BYTES"]),
                )
                if built is None or not built.is_file():
                    return jsonify(error="File not found"), 404
                if built.stat().st_size > PREVIEW_MAX_BYTES:
                    built.unlink(missing_ok=True)
                    return jsonify(error="File not found"), 404
                payload = built.read_bytes()
        return flask_app.response_class(payload, mimetype="audio/mpeg")
```

Do not touch `source_choices` or statuses.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_source_preview_route_serves_cached_clip_for_stored_id tests/test_app.py::test_source_preview_403_is_404_and_leaves_picker tests/test_app.py::test_job_preview_lock_serializes_builders tests/test_app.py::test_source_thumbnail_allows_only_stored_id tests/test_app.py::test_choose_source_routes_require_failed_stored_id`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Serve same-origin leftover source preview clips."
```

---

### Task 3: Play control in the source dialog

**Files:**
- Modify: `templates/index.html` (`#source-dialog`)
- Modify: `static/app.js` (`appendSourceCards` and dialog close)
- Modify: `static/style.css` (after `.source-card .button`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: GET `/tracks/<index>/source-previews/<id>` from Task 2
- Produces: `#source-dialog-audio`, `.source-preview` Play buttons, one-at-a-time playback

- [ ] **Step 1: Write the failing contract tests**

In `test_render_includes_accessibility_and_local_ui_contract` add:

```python
    assert b'id="source-dialog-audio"' in response.data
```

Add after `test_source_dialog_load_more_is_a_non_submit_button`:

```python
def test_source_dialog_preview_play_is_a_non_submit_button():
    html = Path("templates/index.html").read_text(encoding="utf-8")
    assert 'id="source-dialog-audio"' in html
    js = Path("static/app.js").read_text(encoding="utf-8")
    assert "source-previews/" in js
    assert "Loading preview" in js
    assert "Preview unavailable" in js
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert ".source-card-actions" in css
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_source_dialog_preview_play_is_a_non_submit_button`

Expected: FAIL (missing `source-dialog-audio` / `source-previews/`)

- [ ] **Step 3: HTML**

Replace the dialog block in `templates/index.html` with:

```html
    <dialog id="source-dialog" aria-labelledby="source-dialog-title">
      <form method="dialog" class="source-dialog-chrome">
        <h2 id="source-dialog-title">Choose a source</h2>
        <p id="source-dialog-meta"></p>
        <div id="source-dialog-cards" class="source-cards"></div>
        <audio id="source-dialog-audio" preload="none"></audio>
        <div class="source-dialog-actions">
          <button class="button button-quiet" id="source-dialog-more" type="button" hidden>Load more</button>
          <button class="button button-quiet" id="source-dialog-close" value="cancel">Close</button>
        </div>
      </form>
    </dialog>
```

- [ ] **Step 4: JS playback**

Next to `sourceMore`, add:

```javascript
  const sourceAudio = document.getElementById("source-dialog-audio");
  let previewButton = null;
```

In `finalizeSourceDialogClose` / before invalidate, stop audio:

```javascript
    if (sourceAudio) {
      sourceAudio.pause();
      sourceAudio.removeAttribute("src");
      sourceAudio.load();
    }
    if (previewButton && previewButton.dataset.previewState !== "unavailable") {
      previewButton.textContent = "Play";
      previewButton.disabled = false;
    }
    previewButton = null;
```

Replace `card.append(image, heading, channel, use)` with a Play button and actions row. Keep **Use this source** as it is. Add:

```javascript
      const play = document.createElement("button");
      play.type = "button";
      play.className = "button button-quiet source-preview";
      play.textContent = "Play";
      play.addEventListener("click", () => {
        if (play.disabled || play.dataset.previewState === "unavailable") return;
        if (previewButton === play && sourceAudio && !sourceAudio.paused) {
          sourceAudio.pause();
          play.textContent = "Play";
          return;
        }
        if (previewButton && previewButton !== play && previewButton.dataset.previewState !== "unavailable") {
          previewButton.textContent = "Play";
          previewButton.disabled = false;
        }
        previewButton = play;
        play.textContent = "Loading preview…";
        if (!sourceAudio) return;
        sourceAudio.pause();
        sourceAudio.src = `/tracks/${index}/source-previews/${encodeURIComponent(source.id)}`;
        const playAttempt = sourceAudio.play();
        if (playAttempt && typeof playAttempt.then === "function") {
          playAttempt.then(() => {
            if (previewButton === play) play.textContent = "Pause";
          }).catch(() => {
            play.dataset.previewState = "unavailable";
            play.textContent = "Preview unavailable";
            play.disabled = true;
          });
        }
      });
      const actions = document.createElement("div");
      actions.className = "source-card-actions";
      actions.append(play, use);
      card.append(image, heading, channel, actions);
```

On `sourceAudio` `error` (once at setup, not per card):

```javascript
  sourceAudio?.addEventListener("error", () => {
    if (!previewButton) return;
    previewButton.dataset.previewState = "unavailable";
    previewButton.textContent = "Preview unavailable";
    previewButton.disabled = true;
  });
  sourceAudio?.addEventListener("pause", () => {
    if (previewButton && previewButton.dataset.previewState !== "unavailable" && sourceAudio.paused) {
      previewButton.textContent = "Play";
    }
  });
  sourceAudio?.addEventListener("playing", () => {
    if (previewButton && previewButton.dataset.previewState !== "unavailable") {
      previewButton.textContent = "Pause";
    }
  });
```

Do not POST `/choose-source` from Play. Do not call `setTrackState` queued.

`disableSourceCardButtons` currently disables every `button` inside `.source-cards`, including Play. Change it to disable only `.button-primary` (Use this source), not `.source-preview`, so a failed Use this source can still preview. `sourceCardButtons` used for busy state should be `sourceCards.querySelectorAll(".button-primary")`.

- [ ] **Step 5: CSS**

Replace `.source-card .button { grid-column: 2; justify-self: start; }` with:

```css
.source-card-actions { grid-column: 2; display: flex; gap: 8px; flex-wrap: wrap; }
#source-dialog-audio { display: none; }
```

- [ ] **Step 6: Run tests and syntax check**

Run: `python -m pytest -q tests/test_app.py::test_render_includes_accessibility_and_local_ui_contract tests/test_app.py::test_source_dialog_preview_play_is_a_non_submit_button tests/test_app.py::test_source_dialog_load_more_is_a_non_submit_button tests/test_app.py::test_source_preview_route_serves_cached_clip_for_stored_id`

Then: `python -m pytest -q`

Then: `node --check static/app.js`

Expected: all PASS; `node --check` exits 0.

- [ ] **Step 7: Commit**

```bash
git add templates/index.html static/app.js static/style.css tests/test_app.py
git commit -m "Play a 30-second leftover source preview in Choose source."
```

---

## Spec coverage

| Spec requirement | Task |
|---|---|
| GET `/tracks/<index>/source-previews/<id>` stored-id only, 404 otherwise | 2 |
| 30s range, 5 MB cap, MP3, job dir cache `preview-<id>.mp3` | 1 |
| Not library / not `job.files` / not Saved | 1, 2 |
| `preview_lock` one build at a time | 1 (`Job.preview_lock`), 2 (used in route) |
| Failed build leaves picker and failed status | 2 |
| CSP `media-src 'self'`, no YouTube frame | 2 |
| Play on each card, Pause, one at a time, stop on close | 3 |
| Preview unavailable; Use this source stays | 3 |
| No pasted URL / no embed | all |
| Load more cards get Play | 3 (`appendSourceCards`) |
