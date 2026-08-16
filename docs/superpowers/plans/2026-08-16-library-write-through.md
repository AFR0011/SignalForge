# Library Write-Through Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** On local runs, move each finished MP3 into `Music/SignalForge` (Title Case title, suffix on collision) so a long queue is not stopped by the 500 MB job disk budget.

**Architecture:** After tagging in the job directory, non-production `process_song` allocates a name under a process lock and `os.replace`s the file into `LIBRARY_ROOT`. The job releases the reservation without `retain_artifact`. Production is unchanged. A CSRF `POST /library-root` exists only as a fallback when the default folder cannot be used.

**Tech Stack:** Flask, Flask-SocketIO, pathlib, pytest, vanilla JS.

## Global Constraints

- Write-through is on only when `PRODUCTION` is false (`_production_requested` / `app.config["PRODUCTION"]`).
- Default library root is `Path.home() / "Music" / "SignalForge"`. Tests MUST set `LIBRARY_ROOT` to a temp directory and must never write under the developer’s real Music folder.
- Filenames use `format_title` then Windows-unsafe strip; artist is not in the name. First file `Halo.mp3`, then `Halo (2).mp3`. Never replace a non-empty library file. Replace only a zero-byte leftover.
- **Start selected** and **Retry failed** keep their current meaning. Saved (`success`) indices stay skipped.
- **Choose source** is unchanged. Do not add Load more or excluded top hits.
- Do not raise `MAX_JOB_BYTES`, `ZIP_MAX_BYTES`, or `TASK_BYTE_RESERVATION`.
- Do not hit live YouTube or iTunes in tests; mock yt-dlp and HTTP.
- `git add` only task files. Never `git add -A`. Do not commit `.env`, `AGENTS.md`, workflow docs, or `.cursor`.
- Work on branch `library-write-through` from `main`. Do not commit on `main`.

## File map

- `app.py` — helpers, config, write-through in `process_song`, `POST /library-root`, render flags.
- `templates/index.html` — Saved metric, destination copy, ZIP hidden when write-through is on.
- `static/app.js` — hide ZIP when write-through, disable Start when destination unusable, Saved vs Download.
- `static/style.css` — destination helper if existing tokens are not enough.
- `tests/test_app.py` / `tests/conftest.py` — temp `LIBRARY_ROOT`.
- `README.md` — one sentence on local Music/SignalForge.
- `.env.example` — comment that the library path is not an env var.

Do not split `app.py`.

---

### Task 1: Library filename and path helpers

**Files:**
- Modify: `app.py` (after `format_title`)
- Modify: `tests/conftest.py` (set `LIBRARY_ROOT` on the test app)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `format_title(raw_title: str) -> str`
- Produces:
  - `LibraryWriteError(Exception)`
  - `library_filename_stem(raw_title: str) -> str`
  - `default_library_root() -> Path`
  - `ensure_library_root(root: Path) -> Path`
  - `safe_library_path(root: Path, filename: str) -> Path`
  - `save_mp3_to_library(source: Path, root: Path, stem: str) -> str` (returns destination name; process lock covers allocate+move)

- [ ] **Step 1: Write the failing tests**

Add after the production-secret tests in `tests/test_app.py`:

```python
def test_library_filename_stem_is_title_case_song_only():
    assert application.library_filename_stem("halo (feat. drowsy)") == "Halo"
    assert application.library_filename_stem("it's time") == "It's Time"
    assert application.library_filename_stem('a/b:c*d?e"f<g>h|i') == "Abcdefghi"
    assert application.library_filename_stem("   ") == "Track"


def test_save_mp3_to_library_suffixes_and_replaces_empty_only(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    first = tmp_path / "one.mp3"
    first.write_bytes(b"one")
    assert application.save_mp3_to_library(first, root, "Halo") == "Halo.mp3"
    assert (root / "Halo.mp3").read_bytes() == b"one"
    second = tmp_path / "two.mp3"
    second.write_bytes(b"two")
    assert application.save_mp3_to_library(second, root, "Halo") == "Halo (2).mp3"
    assert (root / "Halo.mp3").read_bytes() == b"one"
    empty = root / "Halo (2).mp3"
    empty.write_bytes(b"")
    third = tmp_path / "three.mp3"
    third.write_bytes(b"three")
    assert application.save_mp3_to_library(third, root, "Halo") == "Halo (2).mp3"
    assert (root / "Halo (2).mp3").read_bytes() == b"three"


def test_safe_library_path_rejects_escape(tmp_path):
    root = tmp_path / "library"
    root.mkdir()
    with pytest.raises(ValueError):
        application.safe_library_path(root, "../outside.mp3")
```

In `tests/conftest.py`, add `"LIBRARY_ROOT": str(tmp_path / "library")` to the `create_app` mapping so later tasks cannot write to real Music.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_library_filename_stem_is_title_case_song_only tests/test_app.py::test_save_mp3_to_library_suffixes_and_replaces_empty_only tests/test_app.py::test_safe_library_path_rejects_escape`

Expected: FAIL (functions missing)

- [ ] **Step 3: Implement helpers in `app.py`**

After `SECRET_PLACEHOLDERS`:

```python
WINDOWS_UNSAFE_FILENAME = re.compile(r'[\\/:*?"<>|\x00-\x1f]')
```

After `format_title`:

```python
class LibraryWriteError(RuntimeError):
    pass


def library_filename_stem(raw_title: str) -> str:
    titled = format_title(raw_title)
    cleaned = WINDOWS_UNSAFE_FILENAME.sub("", titled)
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" .")
    return (cleaned[:96].rstrip(" .") or "Track")


def default_library_root() -> Path:
    return Path.home() / "Music" / "SignalForge"


def ensure_library_root(root: Path) -> Path:
    resolved = root.expanduser().resolve()
    try:
        resolved.mkdir(mode=0o700, parents=True, exist_ok=True)
    except OSError as exc:
        raise LibraryWriteError("Could not create the library folder") from exc
    if not resolved.is_dir() or not os.access(resolved, os.W_OK):
        raise LibraryWriteError("Library folder is not writable")
    return resolved


def safe_library_path(root: Path, filename: str) -> Path:
    if not filename or filename != Path(filename).name:
        raise ValueError("Invalid filename")
    resolved_root = root.resolve()
    path = (resolved_root / filename).resolve()
    if path.parent != resolved_root:
        raise ValueError("Artifact is outside the library root")
    return path


_library_name_lock = threading.Lock()


def save_mp3_to_library(source: Path, root: Path, stem: str) -> str:
    if not source.is_file():
        raise LibraryWriteError("Downloaded file is missing")
    resolved_root = ensure_library_root(root)
    with _library_name_lock:
        destination = _allocate_library_path_locked(resolved_root, stem)
        try:
            os.replace(source, destination)
        except OSError:
            try:
                shutil.copy2(source, destination)
                source.unlink()
            except OSError as exc:
                raise LibraryWriteError("Could not save the file to the library folder") from exc
        return destination.name


def _allocate_library_path_locked(root: Path, stem: str) -> Path:
    candidate = safe_library_path(root, f"{stem}.mp3")
    if not candidate.exists() or candidate.stat().st_size == 0:
        return candidate
    suffix = 2
    while True:
        candidate = safe_library_path(root, f"{stem} ({suffix}).mp3")
        if not candidate.exists() or candidate.stat().st_size == 0:
            return candidate
        suffix += 1
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest -q tests/test_app.py::test_library_filename_stem_is_title_case_song_only tests/test_app.py::test_save_mp3_to_library_suffixes_and_replaces_empty_only tests/test_app.py::test_safe_library_path_rejects_escape`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py tests/conftest.py
git commit -m "Add Title Case library filenames with collision suffixes."
```

---

### Task 2: Library root config and POST /library-root

**Files:**
- Modify: `app.py` (`create_app` mapping, `render_current`, new route near `/download`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `ensure_library_root`, `default_library_root`, `mutation_job`, `LibraryWriteError`
- Produces: `app.config["LIBRARY_ROOT"]` (str), `app.config["WRITE_THROUGH"]` (bool, `not PRODUCTION`), `POST /library-root` JSON `{ "path": str }` → 200 `{ "library_root": "<absolute>" }` / 400 / 409. Production always 409.

- [ ] **Step 1: Write the failing tests**

```python
def test_library_root_route_sets_writable_fallback(app, client, tmp_path):
    upload_csv(app, client)
    token = csrf_for(app, client)
    blocked = tmp_path / "blocked"
    blocked.mkdir()
    blocked.chmod(0o500)
    app.config["LIBRARY_ROOT"] = str(blocked)
    no_csrf = client.post("/library-root", json={"path": str(tmp_path / "ok")})
    assert no_csrf.status_code == 400
    fallback = tmp_path / "ok"
    ok = client.post("/library-root", json={"path": str(fallback)}, headers={"X-CSRFToken": token})
    assert ok.status_code == 200
    assert Path(ok.json["library_root"]) == fallback.resolve()
    assert app.config["LIBRARY_ROOT"] == str(fallback.resolve())


def test_library_root_route_rejected_in_production(tmp_path):
    prod = application.create_app(
        {
            "TESTING": True,
            "PRODUCTION": True,
            "SECRET_KEY": "a-valid-production-secret-with-more-than-32-characters",
            "DATA_ROOT": str(tmp_path / "jobs"),
            "LIBRARY_ROOT": str(tmp_path / "library"),
            "RATELIMIT_ENABLED": False,
        }
    )
    client = prod.test_client()
    upload_csv(prod, client)
    token = csrf_for(prod, client)
    response = client.post(
        "/library-root",
        json={"path": str(tmp_path / "other")},
        headers={"X-CSRFToken": token},
    )
    assert response.status_code == 409
```

If chmod 0o500 is unreliable on Windows, the first test may use a path that `ensure_library_root` cannot create (e.g. `tmp_path / "missing-parent" / "x"` after making `missing-parent` a file). Prefer a file-as-parent:

```python
blocker = tmp_path / "not-a-dir"
blocker.write_text("x", encoding="utf-8")
app.config["LIBRARY_ROOT"] = str(blocker)
```

Do not assert chmod-only failures on Windows.

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_library_root_route_sets_writable_fallback tests/test_app.py::test_library_root_route_rejected_in_production`

Expected: FAIL (404 or missing WRITE_THROUGH)

- [ ] **Step 3: Implement config + route**

In `create_app` `from_mapping`, after `ARTWORK_MAX_BYTES`:

```python
LIBRARY_ROOT=None,
WRITE_THROUGH=None,
```

After `if flask_app.config["TASK_BYTE_RESERVATION"] is None:`:

```python
if flask_app.config["WRITE_THROUGH"] is None:
    flask_app.config["WRITE_THROUGH"] = not bool(flask_app.config["PRODUCTION"])
if not flask_app.config.get("LIBRARY_ROOT"):
    flask_app.config["LIBRARY_ROOT"] = str(default_library_root())
```

Pass into `render_current`:

```python
write_through=flask_app.config["WRITE_THROUGH"],
library_root=flask_app.config["LIBRARY_ROOT"],
library_ready=True,
```

`library_ready` for this task may stay `True`; Task 5 will probe writability for the template. The route must still exist.

Near `/download`, using `mutation_job` and `@limiter.limit("20 per minute")`:

```python
@flask_app.route("/library-root", methods=["POST"])
@limiter.limit("20 per minute")
def set_library_root() -> Any:
    job, error_response = mutation_job()
    if error_response:
        return error_response
    if not flask_app.config["WRITE_THROUGH"]:
        return jsonify(error="Library folder can only be changed on a local run"), 409
    payload = request.get_json(silent=True) or {}
    raw = payload.get("path")
    if not isinstance(raw, str) or not raw.strip():
        return jsonify(error="Choose a library folder"), 400
    try:
        resolved = ensure_library_root(Path(raw.strip()))
    except LibraryWriteError as exc:
        return jsonify(error=str(exc)), 409
    flask_app.config["LIBRARY_ROOT"] = str(resolved)
    return jsonify(library_root=str(resolved))
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest -q tests/test_app.py::test_library_root_route_sets_writable_fallback tests/test_app.py::test_library_root_route_rejected_in_production`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py tests/conftest.py
git commit -m "Add a local fallback route for the library folder."
```

---

### Task 3: Write-through after tag in process_song

**Files:**
- Modify: `app.py` (`process_song` after `tag_mp3_file`)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `save_mp3_to_library`, `library_filename_stem`, `app.config["WRITE_THROUGH"]`, `app.config["LIBRARY_ROOT"]`, `LibraryWriteError`
- Produces: On local success, `publish("success", "Saved", 100, library_filename=name)` with no `download_url`; `job.files` / `retained_bytes` unchanged. On `LibraryWriteError`, do **not** call `_remove_task_outputs`; fail with `Could not save the file to the library folder.` and keep the job MP3. Production still uses `retain_artifact` and `Ready to download`.

- [ ] **Step 1: Write the failing tests**

Follow the existing `process_song` monkeypatch pattern (`resolve_ffmpeg`, `download_song_from_youtube` writing bytes, `tag_mp3_file` no-op, `emit` no-op, `reserve_indices`).

```python
def test_process_song_write_through_saves_title_case_and_skips_retain(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_mp3(_query, output_base, _ffmpeg, _progress, _max_source, **_kwargs):
        output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "download_song_from_youtube", write_mp3)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    library = Path(app.config["LIBRARY_ROOT"])
    assert (library / "Halo.mp3").read_bytes() == b"audio"
    assert job.files == {}
    assert job.retained_bytes == 0
    assert job.statuses[0]["status"] == "success"
    assert job.statuses[0]["message"] == "Saved"
    assert job.statuses[0]["library_filename"] == "Halo.mp3"
    assert "download_url" not in job.statuses[0]


def test_process_song_write_through_off_in_production_retains_job_file(tmp_path, monkeypatch):
    prod = application.create_app(
        {
            "TESTING": True,
            "PRODUCTION": True,
            "SECRET_KEY": "a-valid-production-secret-with-more-than-32-characters",
            "DATA_ROOT": str(tmp_path / "jobs"),
            "LIBRARY_ROOT": str(tmp_path / "library"),
            "RATELIMIT_ENABLED": False,
            "TASK_BYTE_RESERVATION": 10,
            "MAX_JOB_BYTES": 100,
        }
    )
    client = prod.test_client()
    upload_csv(prod, client)
    job = current_job(client)
    sio = prod.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        application,
        "download_song_from_youtube",
        lambda _q, output_base, *_a, **_k: output_base.with_suffix(".mp3").write_bytes(b"audio"),
    )
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(prod, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert job.files[0].endswith(".mp3")
    assert job.retained_bytes > 0
    assert "download_url" in job.statuses[0]
    assert not (Path(prod.config["LIBRARY_ROOT"]) / "Halo.mp3").exists()


def test_process_song_library_move_failure_keeps_job_file(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        application,
        "download_song_from_youtube",
        lambda _q, output_base, *_a, **_k: output_base.with_suffix(".mp3").write_bytes(b"audio"),
    )
    monkeypatch.setattr(
        application,
        "save_mp3_to_library",
        lambda *args, **kwargs: (_ for _ in ()).throw(application.LibraryWriteError("Could not save the file to the library folder")),
    )
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert job.statuses[0]["status"] == "failed"
    assert "library folder" in job.statuses[0]["message"]
    assert list(job.directory.glob("*.mp3"))
    assert job.files == {}
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest -q tests/test_app.py::test_process_song_write_through_saves_title_case_and_skips_retain tests/test_app.py::test_process_song_write_through_off_in_production_retains_job_file tests/test_app.py::test_process_song_library_move_failure_keeps_job_file`

Expected: FAIL (still Ready to download / file deleted on fail)

- [ ] **Step 3: Implement write-through in `process_song`**

Replace the block from `tag_mp3_file` through `publish("success"...` with:

```python
            tag_mp3_file(filepath, song, int(app.config["ARTWORK_MAX_BYTES"]))
            actual_bytes = filepath.stat().st_size
            if actual_bytes > int(app.config["MAX_ARTIFACT_BYTES"]):
                raise ValueError("Downloaded file exceeds the configured size limit")
            if app.config["WRITE_THROUGH"]:
                library_name = save_mp3_to_library(
                    filepath,
                    Path(app.config["LIBRARY_ROOT"]),
                    library_filename_stem(song["Song"]),
                )
                with job.lock:
                    job.source_choices.pop(index, None)
                    job.forced_sources.pop(index, None)
                    job.failed.discard(index)
                publish("success", "Saved", 100, library_filename=library_name)
            else:
                retained = job_registry.retain_artifact(
                    job,
                    index,
                    filename,
                    actual_bytes,
                    int(app.config["MAX_JOB_BYTES"]),
                    int(app.config["MAX_TOTAL_JOB_BYTES"]),
                )
                if not retained:
                    raise ValueError("Downloaded file exceeds the remaining per-job disk budget")
                with job.lock:
                    job.source_choices.pop(index, None)
                    job.forced_sources.pop(index, None)
                artifact_url = f"/jobs/{job_id}/files/{quote(filename)}"
                publish("success", "Ready to download", 100, download_url=artifact_url)
```

In `except Exception as exc:`:

- If `isinstance(exc, LibraryWriteError)`: do **not** `_remove_task_outputs`. Message is `str(exc)` or `Could not save the file to the library folder.` `can_choose_source` is false unless leftovers already apply from a YouTube failure (they will not on a move failure).
- Else: keep today’s `_remove_task_outputs` when `not retained`.

Introduce `keep_outputs = isinstance(exc, LibraryWriteError)` before the delete.

`release_task` still runs in `finally`.

- [ ] **Step 4: Run tests**

Run the three tests plus `python -m pytest -q tests/test_app.py::test_process_song_stores_picker_sources_and_can_choose_flag tests/test_app.py::test_actual_byte_overflow_deletes_output_and_reconciles_counters`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Save finished local tracks into the library folder."
```

---

### Task 4: Retry move without a second search

**Files:**
- Modify: `app.py` (`process_song` start of try)
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: existing job MP3 at `deterministic_filename` path
- Produces: If `WRITE_THROUGH` and that `.mp3` already exists and is non-empty, skip `download_song_from_youtube` / `tag_mp3_file` and only call `save_mp3_to_library`.

- [ ] **Step 1: Write the failing test**

```python
def test_process_song_retries_library_move_without_search(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    filename = application.deterministic_filename(0, job.songs[0])
    existing = job.directory / filename
    existing.write_bytes(b"already")
    calls = {"download": 0}

    def boom(*_args, **_kwargs):
        calls["download"] += 1
        raise AssertionError("search should not run")

    monkeypatch.setattr(application, "download_song_from_youtube", boom)
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: (_ for _ in ()).throw(AssertionError("tag")))
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert calls["download"] == 0
    assert (Path(app.config["LIBRARY_ROOT"]) / "Halo.mp3").read_bytes() == b"already"
    assert job.statuses[0]["message"] == "Saved"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest -q tests/test_app.py::test_process_song_retries_library_move_without_search`

Expected: FAIL (`search should not run`)

- [ ] **Step 3: Skip download when the job MP3 already exists**

After computing `filepath` / `output_base`, before `download_song_from_youtube`:

```python
            reuse_job_file = bool(
                app.config["WRITE_THROUGH"]
                and filepath.is_file()
                and filepath.stat().st_size > 0
            )
            if not reuse_job_file:
                download_song_from_youtube(...)
                tag_mp3_file(...)
            actual_bytes = filepath.stat().st_size
            ...
```

- [ ] **Step 4: Run test**

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add app.py tests/test_app.py
git commit -m "Retry library saves from the job file without searching again."
```

---

### Task 5: UI, README, and full verification

**Files:**
- Modify: `templates/index.html`, `static/app.js`, `static/style.css` (only if needed), `app.py` (`render_current` / `library_ready`), `README.md`, `.env.example`
- Test: `tests/test_app.py`

**Interfaces:**
- Consumes: `WRITE_THROUGH`, `LIBRARY_ROOT`, `ensure_library_root`
- Produces: Overview destination, **Saved** metric, ZIP hidden when write-through, Start disabled when library unusable, `data-write-through` / `data-library-ready` on `body`.

- [ ] **Step 1: Write the failing render test**

```python
def test_render_local_workspace_shows_saved_destination_and_hides_zip(app, client):
    upload_csv(app, client)
    page = client.get("/")
    assert page.status_code == 200
    assert b'id="metric-saved"' in page.data
    assert b"Music\\SignalForge" in page.data or b"Music/SignalForge" in page.data
    assert b'id="download-zip"' in page.data
    assert b"hidden" in page.data
    assert b'data-write-through="true"' in page.data
```

Probe `ensure_library_root` in `render_current` when `WRITE_THROUGH` so `library_ready` is false if mkdir/write fails. Show **Change folder** only when `not library_ready`. Destination control: `<p id="library-destination">` plus hidden `#library-fallback` form (path input + submit) visible when not ready. Fallback submits JSON to `/library-root`.

- [ ] **Step 2: Run test to verify it fails**

Expected: FAIL (`metric-saved` missing)

- [ ] **Step 3: Template + JS**

`body` attributes: `data-write-through="{{ 'true' if write_through else 'false' }}"` `data-library-ready="{{ 'true' if library_ready else 'false' }}"`.

Rename `id="metric-ready"` to `id="metric-saved"` and label **Saved**.

ZIP button: `hidden` if `write_through` or `not job.files`.

In `static/app.js`:
- Read `body.dataset.writeThrough === "true"`.
- `updateSummary`: keep counting `success` into `#metric-saved`. If write-through, `zipButton.hidden = true` always.
- `setTrackState`: show download link only when `data.download_url` is present (already true).
- If `data-library-ready` is false, disable `#download-selected` and `#retry-failed` until `/library-root` succeeds.
- Wire fallback submit to `POST /library-root`; on 200, enable Start, hide fallback, update destination text, toast success.
- Do not toast every Saved row.

`README.md` source-processing paragraph: add that local runs move finished MP3s into `Music/SignalForge`.

`.env.example`: comment that the library folder is `Music/SignalForge` by default and is not configured here.

`/download` and `/retry-failed`: if `WRITE_THROUGH` and `ensure_library_root` raises, return 409 with that error (do not queue).

- [ ] **Step 4: Full verification**

Run:

```
python -m py_compile app.py
node --check static/app.js
python -m pytest -q
```

Expected: all tests PASS (count will be previous plus the new ones).

- [ ] **Step 5: Commit**

```bash
git add templates/index.html static/app.js static/style.css app.py tests/test_app.py README.md .env.example
git commit -m "Show the Music/SignalForge destination and hide ZIP on local runs."
```
