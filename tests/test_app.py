from __future__ import annotations

import io
import os
import threading
from pathlib import Path
from typing import Any

import pytest

import app as application
from conftest import csrf_for, current_job, upload_csv


def test_production_rejects_missing_weak_and_placeholder_secrets(tmp_path):
    base = {"TESTING": True, "PRODUCTION": True, "DATA_ROOT": str(tmp_path), "RATELIMIT_ENABLED": False}
    for secret in (None, "short", "dev-secret-change-me", "x" * 31, " " * 40, "x" * 40):
        with pytest.raises(RuntimeError, match="strong SECRET_KEY"):
            application.create_app({**base, "SECRET_KEY": secret})


def test_production_accepts_strong_secret_and_development_generates_one(tmp_path):
    strong = "a-valid-production-secret-with-more-than-32-characters"
    prod = application.create_app(
        {"TESTING": True, "PRODUCTION": True, "SECRET_KEY": strong, "DATA_ROOT": str(tmp_path / "p"), "RATELIMIT_ENABLED": False}
    )
    assert prod.config["SECRET_KEY"] == strong
    assert prod.config["SESSION_COOKIE_SECURE"] is True
    dev = application.create_app(
        {"TESTING": True, "PRODUCTION": False, "SECRET_KEY": None, "DATA_ROOT": str(tmp_path / "d"), "RATELIMIT_ENABLED": False}
    )
    assert application.is_strong_secret(dev.config["SECRET_KEY"])


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


def test_library_root_route_sets_writable_fallback(app, client, tmp_path):
    upload_csv(app, client)
    token = csrf_for(app, client)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    app.config["LIBRARY_ROOT"] = str(blocker)
    no_csrf = client.post("/library-root", json={"path": str(tmp_path / "ok")})
    assert no_csrf.status_code == 400
    fallback = tmp_path / "ok"
    ok = client.post("/library-root", json={"path": str(fallback)}, headers={"X-CSRFToken": token})
    assert ok.status_code == 200
    assert Path(ok.json["library_root"]) == fallback.resolve()
    assert app.config["LIBRARY_ROOT"] == str(fallback.resolve())


def test_render_local_workspace_shows_saved_destination_and_hides_zip(app, client):
    upload_csv(app, client)
    page = client.get("/")
    assert page.status_code == 200
    assert b'id="metric-saved"' in page.data
    assert b"Music\\SignalForge" in page.data or b"Music/SignalForge" in page.data
    assert b'id="download-zip"' in page.data
    assert b"hidden" in page.data
    assert b'data-write-through="true"' in page.data
    assert b'data-library-ready="true"' in page.data
    assert b"Change folder" not in page.data


def test_render_unusable_library_shows_fallback_and_disables_start(app, client, tmp_path):
    upload_csv(app, client)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    app.config["LIBRARY_ROOT"] = str(blocker)
    page = client.get("/")
    assert page.status_code == 200
    assert b'data-library-ready="false"' in page.data
    assert b'id="library-destination"' in page.data
    assert b"Change folder" in page.data
    assert b'id="library-fallback"' in page.data
    assert b'id="download-selected" type="button" disabled' in page.data
    assert b'id="retry-failed" type="button" disabled' in page.data


def test_download_and_retry_reject_unusable_library(app, client, tmp_path, monkeypatch):
    upload_csv(app, client)
    blocker = tmp_path / "not-a-dir"
    blocker.write_text("x", encoding="utf-8")
    app.config["LIBRARY_ROOT"] = str(blocker)
    started = []
    monkeypatch.setattr(
        app.extensions["socketio_instance"], "start_background_task", lambda *args: started.append(args)
    )
    token = csrf_for(app, client)
    download = client.post(
        "/download", json={"selected": [0]}, headers={"X-CSRFToken": token}
    )
    assert download.status_code == 409
    assert "library folder" in download.json["error"].lower()
    assert started == []
    job = current_job(client)
    job.failed.add(0)
    retry = client.post("/retry-failed", json={}, headers={"X-CSRFToken": token})
    assert retry.status_code == 409
    assert "library folder" in retry.json["error"].lower()
    assert started == []


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


def test_valid_upload_renders_and_cookie_session_contains_only_job_id(app, client):
    response = upload_csv(app, client)
    assert response.status_code == 200
    assert b"Halo" in response.data
    assert b"Select all" in response.data
    assert b"Select first" not in response.data
    assert b"loop.index" not in response.data
    with client.session_transaction() as flask_session:
        assert list(flask_session.keys()) == ["job_id"]


def test_render_includes_accessibility_and_local_ui_contract(app, client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'class="skip-link"' in response.data
    assert b'aria-live="polite"' in response.data
    assert b'id="drop-zone"' in response.data
    assert b'id="source-dialog"' in response.data
    assert b"Choose a source" in response.data
    assert b"toastify" not in response.data.lower()
    assert b"/static/socket.io.min.js" in response.data
    assert b"/socket.io/socket.io.js" not in response.data
    script = client.get("/static/socket.io.min.js")
    assert script.status_code == 200
    assert script.mimetype in {"application/javascript", "text/javascript"}
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


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
    assert b'class="button button-quiet choose-source"' in page.data
    assert b'id="source-dialog"' in page.data

    job.statuses[0]["status"] = "queued"
    non_failed_page = client.get("/")
    assert (
        b'class="button button-quiet choose-source" type="button" data-index="0" hidden'
        in non_failed_page.data
    )


@pytest.mark.parametrize("path", ["/this-path-does-not-exist", "/favicon.ico"])
def test_missing_html_pages_return_404_not_500(app, client, path):
    response = client.get(path)
    assert response.status_code == 404
    assert response.mimetype == "text/html"
    assert b"The requested resource was not found" in response.data


@pytest.mark.parametrize(
    "csv_text, expected",
    [
        ('Song,Artist\n"broken,Starling\n', b"CSV is malformed"),
        ("Title,Artist\nHalo,Starling\n", b"Song and Artist"),
        ("Song,Artist\n,Starling\n", b"requires both Song and Artist"),
        ("Song,Artist\nHalo,Starling,extra\n", b"too many fields"),
    ],
)
def test_invalid_csv_errors_are_clear(app, client, csv_text, expected):
    response = upload_csv(app, client, csv_text)
    assert response.status_code == 400
    assert expected in response.data


def test_csv_byte_row_and_field_limits(app, client):
    oversized = "Song,Artist\n" + ("A" * 520) + ",B\n"
    assert b"byte limit" in upload_csv(app, client, oversized).data
    too_many_rows = "Song,Artist\nA,B\nC,D\nE,F\nG,H\n"
    assert b"3-row limit" in upload_csv(app, client, too_many_rows).data
    long_field = "Song,Artist\n" + ("A" * 41) + ",B\n"
    assert b"longer than 40" in upload_csv(app, client, long_field).data


def test_upload_and_mutations_require_csrf(app, client):
    client.get("/")
    response = client.post(
        "/upload",
        data={"csv_file": (io.BytesIO(b"Song,Artist\nA,B\n"), "a.csv")},
        content_type="multipart/form-data",
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 400
    assert response.json["error"].startswith("CSRF")
    assert client.post("/download", json={"selected": [0]}).status_code == 400
    assert client.post("/cleanup", json={}).status_code == 400


@pytest.mark.parametrize(
    "selected,error",
    [([], "at least one"), ([0, 1, 2], "no more than 2"), ([0, 0], "duplicate"), ([-1], "out-of-range"), ([2], "out-of-range"), (["0.0"], "invalid")],
)
def test_selection_validation(app, client, monkeypatch, selected, error):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    monkeypatch.setattr(app.extensions["socketio_instance"], "start_background_task", lambda *args: None)
    response = client.post(
        "/download",
        json={"selected": selected},
        headers={"X-CSRFToken": csrf_for(app, client)},
    )
    assert response.status_code == 400
    assert error in response.json["error"]


def test_selection_is_copied_before_background_dispatch(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    calls = []
    monkeypatch.setattr(app.extensions["socketio_instance"], "start_background_task", lambda *args: calls.append(args))
    response = client.post(
        "/download", json={"selected": [1]}, headers={"X-CSRFToken": csrf_for(app, client)}
    )
    assert response.status_code == 202
    assert calls[0][0] is application.process_song
    assert calls[0][-3] == 1
    assert calls[0][-2] == {"Song": "C", "Artist": "D", "Album": "", "Genres": ""}
    assert calls[0][-1] == app.config["TASK_BYTE_RESERVATION"]


def test_worker_runs_without_request_session_and_targets_only_job_room(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    reservation = int(app.config["TASK_BYTE_RESERVATION"])
    application.job_registry.reserve_indices(job, [0], 2, reservation, int(app.config["MAX_JOB_BYTES"]))
    emitted = []
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(sio, "emit", lambda event, payload, **kwargs: emitted.append((event, payload, kwargs)))
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")

    def fake_download(_query, output_base, _ffmpeg, progress, _max_source, **_kwargs):
        progress(None, "Still working")
        output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "download_song_from_youtube", fake_download)
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), reservation)
    assert job.active_count == 0
    assert job.reserved_bytes == 0
    assert job.retained_bytes == 0
    assert job.files == {}
    assert all(item[2]["to"] == application.job_room(job.job_id) for item in emitted)
    assert emitted[-1][1]["message"] == "Saved"
    assert emitted[-1][1]["library_filename"] == "Halo.mp3"
    assert "download_url" not in emitted[-1][1]


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


def test_process_song_empty_picker_stores_no_alternate_sources_message(app, client, monkeypatch):
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
    assert job.statuses[0]["can_choose_source"] is False
    assert job.statuses[0]["message"] == "Download failed. No alternate sources found."


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


def test_process_song_forced_watch_url_non_403_keeps_picker_id(app, client, monkeypatch):
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
        raise application.DownloadError("network")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_forced)
    application.job_registry.reserve_indices(job, [0], 1, 10, 100)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert captured["watch_url"] == "https://www.youtube.com/watch?v=labellabel1"
    assert [item["id"] for item in job.source_choices[0]] == ["labellabel1", "lyriclyric1"]
    assert job.statuses[0]["can_choose_source"] is True
    assert "choose a source" in job.statuses[0]["message"]


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
        json={"index": 0, "video_id": "unboundxyz1"},
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
    monkeypatch.setattr(
        app.extensions["socketio_instance"],
        "start_background_task",
        lambda target, *args, **kwargs: target(*args, **kwargs),
    )
    accepted = client.post(
        "/choose-source",
        json={"index": 0, "video_id": "labellabel1"},
        headers={"X-CSRFToken": token},
    )
    assert accepted.status_code == 202
    if not captured.get("watch_url") and (0 in job.reserved_indices or 0 in job.pending_indices):
        application.process_song(
            app,
            app.extensions["socketio_instance"],
            job.job_id,
            0,
            dict(job.songs[0]),
            job.reservation_sizes.get(0) or app.config["TASK_BYTE_RESERVATION"],
        )
    assert captured.get("watch_url") == "https://www.youtube.com/watch?v=labellabel1"


def test_source_thumbnail_allows_only_stored_id(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    job.failed.add(0)
    job.statuses[0] = {"status": "failed", "index": 0, "job_id": job.job_id, "message": "failed"}
    job.source_choices[0] = [{"id": "labellabel1", "title": "Halo", "channel": "Label", "duration": 201}]
    jpeg = b"\xff\xd8" + b"thumb" + b"\xff\xd9"
    captured: dict[str, Any] = {}

    class FakeResponse:
        status_code = 200
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

    monkeypatch.setattr(application.requests, "get", fake_get)
    missing = client.get("/tracks/0/source-thumbs/unboundxyz1")
    assert missing.status_code == 404
    ok = client.get("/tracks/0/source-thumbs/labellabel1")
    assert ok.status_code == 200
    assert ok.data.startswith(b"\xff\xd8")
    assert captured["url"] == "https://i.ytimg.com/vi/labellabel1/hqdefault.jpg"
    assert captured["allow_redirects"] is False


def test_two_sessions_cannot_join_or_access_files_or_status(app):
    first = app.test_client()
    second = app.test_client()
    upload_csv(app, first)
    second.get("/")
    first_job = current_job(first)
    filename = application.deterministic_filename(0, first_job.songs[0])
    (first_job.directory / filename).write_bytes(b"owned")
    first_job.files[0] = filename

    url = f"/jobs/{first_job.job_id}/files/{filename}"
    assert first.get(url).data == b"owned"
    assert second.get(url).status_code == 404
    assert second.get(f"/api/jobs/{first_job.job_id}").status_code == 404

    sio = app.extensions["socketio_instance"]
    socket_client = sio.test_client(app, flask_test_client=second)
    socket_client.emit("join_job", {"job_id": first_job.job_id})
    received = socket_client.get_received()
    assert any(item["name"] == "join_error" for item in received)


def test_socket_owner_can_join_job_room(app, client):
    client.get("/")
    job = current_job(client)
    socket_client = app.extensions["socketio_instance"].test_client(app, flask_test_client=client)
    socket_client.emit("join_job", {"job_id": job.job_id})
    assert any(item["name"] == "joined_job" for item in socket_client.get_received())


def test_file_requires_allowlist_and_url_is_authoritative(app, client):
    upload_csv(app, client)
    job = current_job(client)
    unlisted = job.directory / "unlisted.mp3"
    unlisted.write_bytes(b"no")
    assert client.get(f"/jobs/{job.job_id}/files/unlisted.mp3").status_code == 404
    filename = application.deterministic_filename(0, job.songs[0])
    (job.directory / filename).write_bytes(b"yes")
    job.files[0] = filename
    response = client.get(f"/api/jobs/{job.job_id}")
    assert response.json["files"]["0"] == f"/jobs/{job.job_id}/files/{filename}"


def test_cleanup_is_post_only_idempotent_and_rejects_active(app, client):
    upload_csv(app, client)
    job = current_job(client)
    assert client.get("/cleanup").status_code == 405
    job.active_count = 1
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 409
    job.active_count = 0
    old_directory = job.directory
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 200
    assert not old_directory.exists()
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": response.json["csrf_token"]})
    assert response.status_code == 200


def test_cleanup_refuses_path_outside_data_root(app, client, tmp_path):
    client.get("/")
    job = current_job(client)
    outside = tmp_path / "outside"
    outside.mkdir()
    marker = outside / "keep.txt"
    marker.write_text("keep")
    job.directory = outside
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 409
    assert marker.read_text() == "keep"


def test_other_session_cannot_cleanup_job(app):
    first = app.test_client()
    second = app.test_client()
    upload_csv(app, first)
    first_job = current_job(first)
    second.get("/")
    response = second.post(
        "/cleanup",
        json={"job_id": first_job.job_id},
        headers={"X-CSRFToken": application._csrf_token(app, first_job.job_id)},
    )
    assert response.status_code == 400
    assert first_job.directory.exists()


def test_zip_uses_allowlisted_files_and_enforces_total_cap(app, client):
    upload_csv(app, client)
    job = current_job(client)
    first = job.directory / "first.mp3"
    first.write_bytes(b"x" * 65)
    job.files[0] = first.name
    response = client.post("/download_zip", headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 413
    first.write_bytes(b"small")
    response = client.post("/download_zip", headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 200
    assert response.mimetype == "application/zip"
    assert response.data.startswith(b"PK")


def test_ffmpeg_override_and_fallback(tmp_path, monkeypatch):
    executable = tmp_path / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
    executable.write_bytes(b"binary")
    executable.chmod(0o755)
    assert application.resolve_ffmpeg(str(executable)) == str(executable.resolve())
    with pytest.raises(RuntimeError, match="executable"):
        application.resolve_ffmpeg(str(tmp_path / "missing"))
    monkeypatch.delenv("FFMPEG_PATH", raising=False)
    monkeypatch.setattr(application.imageio_ffmpeg, "get_ffmpeg_exe", lambda: str(executable))
    assert application.resolve_ffmpeg() == str(executable.resolve())


def test_js_runtime_override_path_lookup_and_rejection(tmp_path, monkeypatch):
    executable = tmp_path / ("deno.exe" if os.name == "nt" else "deno")
    executable.write_bytes(b"binary")
    executable.chmod(0o755)
    name, path = application.resolve_js_runtime(str(executable), "deno")
    assert name == "deno"
    assert path == str(executable.resolve())
    node_name, node_path = application.resolve_js_runtime(str(executable), "node")
    assert node_name == "node"
    assert node_path == str(executable.resolve())
    with pytest.raises(RuntimeError, match="executable"):
        application.resolve_js_runtime(str(tmp_path / "missing"))
    with pytest.raises(RuntimeError, match="deno or node"):
        application.resolve_js_runtime(str(executable), "bun")
    monkeypatch.delenv("YTDLP_JS_RUNTIME_PATH", raising=False)
    monkeypatch.delenv("YTDLP_JS_RUNTIME", raising=False)
    monkeypatch.setattr(application.shutil, "which", lambda _name: str(executable))
    found_name, found_path = application.resolve_js_runtime()
    assert found_name == "deno"
    assert found_path == str(executable)
    monkeypatch.setattr(application.shutil, "which", lambda _name: None)
    monkeypatch.setattr(application, "_js_runtime_fallback_paths", lambda _name: [executable])
    fallback_name, fallback_path = application.resolve_js_runtime()
    assert fallback_name == "deno"
    assert fallback_path == str(executable.resolve())
    monkeypatch.setattr(application, "_js_runtime_fallback_paths", lambda _name: [])
    with pytest.raises(RuntimeError, match="JavaScript runtime"):
        application.resolve_js_runtime()


def test_youtube_search_prefers_audio_and_skips_clean_or_video_titles():
    query = application.build_youtube_search_query("Eminem", "Till I Collapse")
    assert '"Eminem"' in query
    assert '"Till I Collapse"' in query
    assert "official audio" in query
    assert "-clean" not in query
    feat_query = application.build_youtube_search_query("Ekoh, Drowsy", "Never Enough (feat. Drowsy)")
    assert '"Never Enough"' in feat_query
    assert "feat" not in feat_query.lower()
    assert application.undesired_youtube_source({"title": "Till I Collapse (Clean Version)"})
    assert application.undesired_youtube_source({"title": "Till I Collapse (Non-Explicit)"})
    assert application.undesired_youtube_source({"title": "Lucky You (8D Audio)"})
    assert application.undesired_youtube_source({"title": "Beautiful Pain (Parody)"})
    assert application.undesired_youtube_source({"title": "No Apologies (2025 Remastered)"})
    assert application.undesired_youtube_source({"title": "Natural + Click, No Drums"})
    assert application.undesired_youtube_source({"title": "No Apologies", "duration": 21})
    assert application.undesired_youtube_source({"title": "8 Mile", "duration": 720})
    assert application.undesired_youtube_source({"title": "Till I Collapse"}, incomplete=True) is None
    assert application.undesired_youtube_source({"title": "Till I Collapse (Official Audio)", "duration": 280}) is None
    assert application.undesired_youtube_source({"title": "Till I Collapse (Official Music Video)", "duration": 280}) is None


def test_select_youtube_source_requires_title_and_artist_and_rejects_variants():
    entries = [
        {"id": "love", "title": "No Love (Official Audio)", "uploader": "EminemVEVO", "duration": 300, "view_count": 9_000_000},
        {"id": "fake-pain", "title": "Eminem ft. Sia - Beautiful Pain (Emotional Rap Anthem)", "uploader": "MH Nacht", "duration": 228, "view_count": 4},
        {"id": "preview", "title": "Eminem No Apologies Lyrics", "uploader": "Halifax Examiner", "duration": 21, "view_count": 57},
        {"id": "click", "title": "Imagine Dragons - Natural + Click, No Drums", "uploader": "andrii", "duration": 150, "view_count": 212},
        {"id": "reupload", "title": "Imagine Dragons - Natural (Official Audio)", "uploader": "Nguyen Thanh Cong", "duration": 192, "view_count": 2},
        {"id": "apologies", "title": "No Apologies", "uploader": "EminemMusic", "duration": 259, "view_count": 15_000_000},
        {"id": "lucky", "title": "Eminem - Lucky You (Official Audio) ft. Joyner Lucas", "uploader": "EminemVEVO", "duration": 244, "view_count": 8_000_000},
        {"id": "pain", "title": "Beautiful Pain", "uploader": "EminemMusic", "duration": 266, "view_count": 27_000_000},
        {"id": "natural", "title": "Imagine Dragons - Natural (Audio)", "uploader": "ImagineDragons", "duration": 191, "view_count": 55_000_000},
    ]
    apologies = application.select_youtube_source(entries, "Eminem", "No Apologies")
    assert apologies is not None and apologies["id"] == "apologies"
    lucky = application.select_youtube_source(entries, "Eminem", "Lucky You")
    assert lucky is not None and lucky["id"] == "lucky"
    pain = application.select_youtube_source(entries, "Eminem, Sia", "Beautiful Pain")
    assert pain is not None and pain["id"] == "pain"
    natural = application.select_youtube_source(entries, "Imagine Dragons", "Natural")
    assert natural is not None and natural["id"] == "natural"
    assert application.select_youtube_source(entries, "Eminem", "Not A Real Song") is None
    assert application.score_youtube_candidate(entries[1], "Eminem, Sia", "Beautiful Pain") is None
    assert application.score_youtube_candidate(entries[2], "Eminem", "No Apologies") is None
    assert application.score_youtube_candidate(entries[3], "Imagine Dragons", "Natural") is None
    assert application.score_youtube_candidate(entries[4], "Imagine Dragons", "Natural") is None


def test_select_youtube_source_skips_movie_clips_and_allows_trusted_fallbacks():
    eight_mile = [
        {
            "id": "lose",
            "title": 'Lose Yourself (From "8 Mile" Soundtrack)',
            "uploader": "EminemMusic",
            "duration": 322,
            "view_count": 9_000_000,
        },
        {
            "id": "movie",
            "title": "8 Mile | Eminem's Final Rap Battles",
            "uploader": "EminemMusic",
            "duration": 395,
            "view_count": 66_000_000,
        },
        {
            "id": "long",
            "title": "8 Mile",
            "uploader": "EminemMusic",
            "duration": 720,
            "view_count": 1_000_000,
        },
        {
            "id": "song",
            "title": "8 Mile",
            "uploader": "EminemMusic",
            "duration": 360,
            "view_count": 48_000_000,
        },
    ]
    chosen = application.select_youtube_source(eight_mile, "Eminem", "8 Mile")
    assert chosen is not None and chosen["id"] == "song"
    assert application.score_youtube_candidate(eight_mile[0], "Eminem", "8 Mile") is None
    assert application.score_youtube_candidate(eight_mile[1], "Eminem", "8 Mile") is None

    never = [
        {
            "id": "video",
            "title": "Ekoh - Never Enough feat. Drowsy (Official Music Video)",
            "uploader": "Ekoh",
            "duration": 281,
            "view_count": 237_150,
        },
        {
            "id": "wrong",
            "title": "Never Enough (feat. Rachel Lorin)",
            "uploader": "C-Lance - Topic",
            "duration": 211,
            "view_count": 148_180,
        },
        {
            "id": "fan",
            "title": "Ekoh - Never Enough (feat. Drowsy) [Audio]",
            "uploader": "BIPOLAR MUSIC",
            "duration": 281,
            "view_count": 12,
        },
    ]
    chosen = application.select_youtube_source(never, "Ekoh, Drowsy", "Never Enough (feat. Drowsy)")
    assert chosen is not None and chosen["id"] == "video"

    nf_entries = [
        {
            "id": "lyric",
            "title": "NF - Turn The Music Up (Lyric Video)",
            "uploader": "NFrealmusic",
            "duration": 207,
            "view_count": 10_625_086,
        },
        {
            "id": "info",
            "title": "Turn The Music Up (Official Audio)",
            "uploader": "InfoMusic",
            "duration": 207,
            "view_count": 50,
        },
    ]
    chosen = application.select_youtube_source(nf_entries, "NF", "Turn The Music Up")
    assert chosen is not None and chosen["id"] == "lyric"
    assert application.channel_is_trusted("InfoMusic", "NF") is False
    assert application.channel_is_trusted("NFrealmusic", "NF") is True

    homicide = [
        {
            "id": "label",
            "title": "Logic - Homicide (feat. Eminem) (Official Audio)",
            "uploader": "Visionary Music Group",
            "duration": 246,
            "view_count": 117_000_000,
        },
        {
            "id": "video",
            "title": "Logic - Homicide ft. Eminem (Official Video)",
            "uploader": "Logic",
            "duration": 433,
            "view_count": 110_000_000,
        },
    ]
    chosen = application.select_youtube_source(homicide, "Logic, Eminem", "Homicide")
    assert chosen is not None and chosen["id"] == "label"
    assert application.score_youtube_candidate(homicide[1], "Logic, Eminem", "Homicide") is not None

    paradise = [
        {
            "id": "coolio",
            "title": "Gangsta's Paradise",
            "uploader": "Coolio",
            "duration": 241,
            "view_count": 37_000_000,
        },
        {
            "id": "label",
            "title": "Coolio - Gangsta's Paradise",
            "uploader": "Tommy Boy",
            "duration": 241,
            "view_count": 33_000_000,
        },
    ]
    chosen = application.select_youtube_source(paradise, "Coolio, L.V.", "Gangsta's Paradise")
    assert chosen is not None and chosen["id"] == "coolio"
    assert application.score_youtube_candidate(paradise[1], "Coolio, L.V.", "Gangsta's Paradise") is not None


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
    attempts: list[str] = []

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
                    {"id": "officialaaa", "title": "Halo Official Audio", "uploader": "Starling - Topic", "duration": 200, "view_count": 9},
                    {"id": "vevovevovev", "title": "Halo Official Audio", "uploader": "StarlingVEVO", "duration": 200, "view_count": 8},
                    {"id": "labellabel1", "title": "Starling - Halo (Official Audio)", "uploader": "Label Records", "duration": 201, "view_count": 99_999},
                ]
            }

        def download(self, queries):
            attempts.append(queries[0])
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
    assert any("officialaaa" in item for item in attempts)
    assert any("vevovevovev" in item for item in attempts)
    assert [item["id"] for item in picker] == ["labellabel1"]


def test_youtube_download_retries_next_result_after_403(tmp_path, monkeypatch):
    output_base = tmp_path / "track"
    attempts: list[str] = []

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
                    {"id": "first", "title": "Halo Official Audio", "uploader": "Starling - Topic"},
                    {"id": "second", "title": "Halo Official Audio", "uploader": "StarlingVEVO"},
                ]
            }

        def download(self, queries):
            attempts.append(queries[0])
            if "first" in queries[0]:
                raise application.DownloadError("ERROR: unable to download video data: HTTP Error 403: Forbidden")
            output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    application.download_song_from_youtube(
        "Starling Halo",
        output_base,
        "ffmpeg",
        lambda *_args: None,
        100,
        artist="Starling",
        title="Halo",
    )
    assert any("first" in item for item in attempts)
    assert any("second" in item for item in attempts)
    assert output_base.with_suffix(".mp3").is_file()


def test_fetch_cover_art_prefers_album_match_and_sends_user_agent(monkeypatch):
    calls: list[dict[str, Any]] = []

    class FakeResponse:
        def __init__(self, payload=None, content=b"", content_type="application/json"):
            self._payload = payload or {}
            self.content = content
            self.headers = {"Content-Type": content_type}

        def raise_for_status(self) -> None:
            return None

        def json(self) -> dict[str, Any]:
            return self._payload

        def iter_content(self, _size: int):
            yield self.content

    def fake_get(url, params=None, timeout=None, stream=False, headers=None):
        calls.append({"url": url, "params": params, "headers": headers, "stream": stream})
        if "itunes.apple.com" in url:
            return FakeResponse(
                {
                    "results": [
                        {"artworkUrl100": "https://example.test/other/100x100bb.jpg", "collectionName": "Curtain Call"},
                        {"artworkUrl100": "https://example.test/show/100x100bb.jpg", "collectionName": "The Eminem Show"},
                    ]
                },
                content_type="text/javascript; charset=utf-8",
            )
        return FakeResponse(content=b"\xff\xd8cover", content_type="image/jpeg")

    monkeypatch.setattr(application.requests, "get", fake_get)
    cover = application.fetch_cover_art("Till I Collapse", "Eminem", 5_000_000, "The Eminem Show")
    assert cover == b"\xff\xd8cover"
    assert calls[0]["params"]["term"] == "Till I Collapse Eminem The Eminem Show"
    assert calls[0]["headers"]["User-Agent"]
    assert "show/600x600bb.jpg" in calls[1]["url"]


def test_sidecar_jpeg_is_used_when_itunes_cover_is_missing(tmp_path, monkeypatch):
    mp3 = tmp_path / "track.mp3"
    mp3.write_bytes(b"audio")
    (tmp_path / "track.jpg").write_bytes(b"\xff\xd8cover")
    monkeypatch.setattr(application, "fetch_cover_art", lambda *_args, **_kwargs: None)
    cover = application.load_cover_art_bytes(
        mp3,
        {"Song": "Halo", "Artist": "Starling"},
        5_000_000,
    )
    assert cover == b"\xff\xd8cover"


def test_js_runtime_discovers_winget_package_layout(tmp_path, monkeypatch):
    packages = tmp_path / "Microsoft" / "WinGet" / "Packages" / "DenoLand.Deno_Microsoft.Winget.Source_8wekyb3d8bbwe"
    packages.mkdir(parents=True)
    executable = packages / ("deno.exe" if os.name == "nt" else "deno")
    executable.write_bytes(b"binary")
    executable.chmod(0o755)
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.delenv("YTDLP_JS_RUNTIME_PATH", raising=False)
    monkeypatch.delenv("YTDLP_JS_RUNTIME", raising=False)
    monkeypatch.setattr(application.shutil, "which", lambda _name: None)
    name, path = application.resolve_js_runtime()
    assert name == "deno"
    assert path == str(executable.resolve())


def test_utilities_are_safe_and_deterministic(tmp_path):
    job_id = "a" * 43
    root = tmp_path / "root"
    root.mkdir()
    assert application.safe_job_directory(root, job_id) == (root / job_id).resolve()
    with pytest.raises(ValueError):
        application.safe_job_directory(root, job_id, tmp_path / "outside")
    song = {"Song": 'Bad / Name (feat. X)', "Artist": 'A:*rtist'}
    filename = application.deterministic_filename(4, song)
    assert filename.startswith("0005-") and filename.endswith(".mp3")
    assert not any(character in filename for character in '\\/:*?"<>|')
    assert application.format_title("TRACK-speed up") == "Track (Sped Up)"


def test_rate_limit_returns_json_429(tmp_path):
    limited = application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "limited"),
            "RATELIMIT_ENABLED": True,
        }
    )
    client = limited.test_client()
    client.get("/")
    token = csrf_for(limited, client)
    responses = [
        client.post("/upload", headers={"Accept": "application/json", "X-CSRFToken": token})
        for _ in range(11)
    ]
    assert responses[-1].status_code == 429
    assert "Too many" in responses[-1].json["error"]


def test_close_and_admission_race_has_one_coherent_winner(tmp_path):
    registry = application.JobRegistry()
    job = registry.create(tmp_path, [{"Song": "A", "Artist": "B"}])
    barrier = threading.Barrier(3)
    outcomes = []

    def admit():
        barrier.wait()
        try:
            registry.reserve_indices(job, [0], 1, 10, 100)
            outcomes.append("admitted")
        except application.JobUnavailableError:
            outcomes.append("admission-closed")

    def close():
        barrier.wait()
        try:
            registry.close_if_idle(job)
            outcomes.append("closed")
        except application.JobBusyError:
            outcomes.append("close-busy")

    threads = [threading.Thread(target=admit), threading.Thread(target=close)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) in (
        sorted(["admitted", "close-busy"]),
        sorted(["closed", "admission-closed"]),
    )
    if "admitted" in outcomes:
        assert registry.get(job.job_id) is job
        assert job.lifecycle == "accepting"
        assert job.active_count == 1
    else:
        assert registry.get(job.job_id) is job
        assert job.lifecycle == "closing"


def test_task_ceiling_starts_prefix_and_queues_remainder(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    app.config["MAX_ACTIVE_TASKS_PER_JOB"] = 1
    calls = []
    monkeypatch.setattr(app.extensions["socketio_instance"], "start_background_task", lambda *args: calls.append(args))
    response = client.post(
        "/download",
        json={"selected": [0, 1]},
        headers={"X-CSRFToken": csrf_for(app, client)},
    )
    job = current_job(client)
    assert response.status_code == 202
    assert response.json["started"] == [0, 1]
    assert calls[0][-3] == 0
    assert len(calls) == 1
    assert job.active_count == 1
    assert job.reserved_indices == {0}
    assert job.pending_indices == [1]
    assert job.statuses[1]["status"] == "queued"


def test_pending_queue_drains_after_task_release(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    app.config.update(MAX_ACTIVE_TASKS_PER_JOB=1, TASK_BYTE_RESERVATION=6, MAX_JOB_BYTES=100, WRITE_THROUGH=False)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    later_starts = []
    monkeypatch.setattr(sio, "start_background_task", lambda *args: later_starts.append(args))
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_audio(_query, output_base, _ffmpeg, _progress, _max_source, **_kwargs):
        output_base.with_suffix(".mp3").write_bytes(b"123456")

    monkeypatch.setattr(application, "download_song_from_youtube", write_audio)
    response = client.post(
        "/download", json={"selected": [0, 1]}, headers={"X-CSRFToken": csrf_for(app, client)}
    )
    assert response.status_code == 202
    assert job.pending_indices == [1]
    assert later_starts[0][-3] == 0
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 6)
    assert job.pending_indices == []
    assert job.reserved_indices == {1}
    assert later_starts[-1][-3] == 1
    assert job.files[0].endswith(".mp3")


def test_pending_work_blocks_cleanup(app, client):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    job = current_job(client)
    application.job_registry.enqueue_indices(job, [0, 1], 1, 1, 100, 1_000)
    application.job_registry.release_task(job, 0, 1)
    assert job.pending_indices == [1]
    assert job.active_count == 0
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 409
    assert application.job_registry.get(job.job_id) is job


def test_full_imported_list_can_be_selected_and_queued(tmp_path, monkeypatch):
    limited = application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "full-select"),
            "RATELIMIT_ENABLED": False,
            "CSV_MAX_ROWS": 5,
            "SELECTION_LIMIT": 5,
            "MAX_ACTIVE_TASKS_PER_JOB": 1,
            "TASK_BYTE_RESERVATION": 1,
            "MAX_JOB_BYTES": 100,
        }
    )
    client = limited.test_client()
    songs = "Song,Artist\n" + "\n".join(f"S{i},A{i}" for i in range(5)) + "\n"
    upload_csv(limited, client, songs)
    monkeypatch.setattr(limited.extensions["socketio_instance"], "start_background_task", lambda *args: None)
    response = client.post(
        "/download",
        json={"selected": [0, 1, 2, 3, 4]},
        headers={"X-CSRFToken": csrf_for(limited, client)},
    )
    job = current_job(client)
    assert response.status_code == 202
    assert response.json["started"] == [0, 1, 2, 3, 4]
    assert job.reserved_indices == {0}
    assert job.pending_indices == [1, 2, 3, 4]
    page = client.get("/")
    assert b"Select all" in page.data
    assert b"Queue the full imported list" in page.data


def test_never_fitting_pending_fails_closed_on_drain(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    app.config.update(MAX_ACTIVE_TASKS_PER_JOB=1, TASK_BYTE_RESERVATION=6, MAX_JOB_BYTES=10, MAX_ARTIFACT_BYTES=10, WRITE_THROUGH=False)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(sio, "start_background_task", lambda *args: None)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_six(_query, output_base, _ffmpeg, _progress, _max_source, **_kwargs):
        output_base.with_suffix(".mp3").write_bytes(b"123456")

    monkeypatch.setattr(application, "download_song_from_youtube", write_six)
    response = client.post(
        "/download", json={"selected": [0, 1]}, headers={"X-CSRFToken": csrf_for(app, client)}
    )
    assert response.status_code == 202
    assert job.pending_indices == [1]
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 6)
    assert job.pending_indices == []
    assert 1 in job.failed
    assert "disk budget" in job.statuses[1]["message"]


def test_cumulative_budget_blocks_second_artifact_before_spawn(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    app.config.update(TASK_BYTE_RESERVATION=6, MAX_JOB_BYTES=10, MAX_ARTIFACT_BYTES=10, WRITE_THROUGH=False)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_six(_query, output_base, _ffmpeg, _progress, _max_source, **_kwargs):
        output_base.with_suffix(".mp3").write_bytes(b"123456")

    monkeypatch.setattr(application, "download_song_from_youtube", write_six)
    application.job_registry.reserve_indices(job, [0], 2, 6, 10)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 6)
    assert job.retained_bytes == 6
    calls = []
    monkeypatch.setattr(sio, "start_background_task", lambda *args: calls.append(args))
    response = client.post(
        "/download", json={"selected": [1]}, headers={"X-CSRFToken": csrf_for(app, client)}
    )
    assert response.status_code == 409
    assert "disk budget" in response.json["error"]
    assert calls == []
    assert job.reserved_bytes == 0


def test_actual_byte_overflow_deletes_output_and_reconciles_counters(app, client, monkeypatch):
    upload_csv(app, client)
    app.config.update(TASK_BYTE_RESERVATION=4, MAX_JOB_BYTES=5, MAX_ARTIFACT_BYTES=10, WRITE_THROUGH=False)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_six(_query, output_base, _ffmpeg, _progress, _max_source, **_kwargs):
        output_base.with_suffix(".mp3").write_bytes(b"123456")

    monkeypatch.setattr(application, "download_song_from_youtube", write_six)
    application.job_registry.reserve_indices(job, [0], 1, 4, 5)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 4)
    assert job.active_count == 0
    assert job.reserved_bytes == 0
    assert job.retained_bytes == 0
    assert job.files == {}
    assert job.failed == {0}
    assert list(job.directory.iterdir()) == []
    assert job.statuses[0]["message"] == "Download failed. You can retry this track."
    assert job.statuses[0].get("can_choose_source") is not True


def test_start_and_worker_failures_release_reservations_and_outputs(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    app.config.update(TASK_BYTE_RESERVATION=10, MAX_JOB_BYTES=100)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(sio, "start_background_task", lambda *args: (_ for _ in ()).throw(RuntimeError("start")))
    response = client.post(
        "/download", json={"selected": [0]}, headers={"X-CSRFToken": csrf_for(app, client)}
    )
    assert response.status_code == 409
    assert job.active_count == 0 and job.reserved_bytes == 0 and job.reserved_indices == set()

    application.job_registry.reserve_indices(job, [1], 2, 10, 100)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def fail_after_partial(_query, output_base, _ffmpeg, _progress, _max_source, **_kwargs):
        output_base.with_suffix(".part").write_bytes(b"partial")
        raise RuntimeError("worker")

    monkeypatch.setattr(application, "download_song_from_youtube", fail_after_partial)
    application.process_song(app, sio, job.job_id, 1, dict(job.songs[1]), 10)
    assert job.active_count == 0 and job.reserved_bytes == 0 and job.reserved_indices == set()
    assert job.retained_bytes == 0 and job.files == {}
    assert list(job.directory.iterdir()) == []


def test_cleanup_deletion_failure_restores_retryable_job(app, client, monkeypatch):
    upload_csv(app, client)
    job = current_job(client)
    filename = "kept.mp3"
    (job.directory / filename).write_bytes(b"1234")
    job.files[0] = filename
    job.retained_bytes = 4
    real_rmtree = application.shutil.rmtree

    def partially_delete_then_fail(path):
        (Path(path) / filename).unlink()
        raise OSError("locked")

    monkeypatch.setattr(application.shutil, "rmtree", partially_delete_then_fail)
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 500
    assert application.job_registry.get(job.job_id) is job
    assert job.lifecycle == "accepting"
    assert job.directory.exists()
    assert job.files == {}
    assert job.retained_bytes == 0
    monkeypatch.setattr(application.shutil, "rmtree", real_rmtree)
    response = client.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(app, client)})
    assert response.status_code == 200


@pytest.mark.parametrize(
    "setting,value",
    [
        ("MAX_SOURCE_BYTES", 0),
        ("MAX_JOBS", 0),
        ("MAX_TOTAL_JOB_BYTES", -1),
        ("JOB_TTL_SECONDS", 0),
    ],
)
def test_new_capacity_configuration_must_be_positive(tmp_path, setting, value):
    config = {
        "TESTING": True,
        "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
        "PRODUCTION": False,
        "DATA_ROOT": str(tmp_path / setting),
        "RATELIMIT_ENABLED": False,
        setting: value,
    }
    with pytest.raises(ValueError, match=setting):
        application.create_app(config)


def test_source_limit_is_passed_to_ytdlp_and_equality_is_allowed(tmp_path, monkeypatch):
    captured = {}
    output_base = tmp_path / "track"

    class FakeYDL:
        def __init__(self, options):
            captured.update(options)

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _queries):
            captured["progress_hooks"][0](
                {"status": "downloading", "total_bytes": 100, "downloaded_bytes": 100}
            )
            captured["queries"] = _queries
            output_base.with_suffix(".mp3").write_bytes(b"audio")

        def extract_info(self, url, download=True):
            captured["search_url"] = url
            return {"entries": [{"id": "abc123", "title": "query Official Audio", "uploader": "query - Topic"}]}

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    application.download_song_from_youtube("query", output_base, "ffmpeg", lambda *_args: None, 100)
    assert captured["max_filesize"] == 100
    assert captured["js_runtimes"] == {"deno": {"path": "deno"}}
    assert captured["search_url"].startswith("ytsearch")
    assert "official audio" in captured["search_url"]
    assert captured["queries"][0].startswith("https://www.youtube.com/watch?v=")
    assert captured["extractor_args"]["youtube"]["player_client"] == ["default", "ios", "-android_sdkless"]
    assert callable(captured["match_filter"])
    assert captured["noplaylist"] is True


@pytest.mark.parametrize("field", ["total_bytes", "total_bytes_estimate", "downloaded_bytes"])
def test_source_hook_aborts_each_known_measure_above_cap(tmp_path, monkeypatch, field):
    output_base = tmp_path / field

    class FakeYDL:
        def __init__(self, options):
            self.options = options

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def download(self, _queries):
            output_base.with_suffix(".part").write_bytes(b"partial")
            self.options["progress_hooks"][0]({"status": "downloading", field: 101})

        def extract_info(self, _url, download=True):
            return {"entries": [{"id": "abc123", "title": "query Official Audio", "uploader": "query"}]}

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    monkeypatch.setattr(application, "resolve_js_runtime", lambda: ("deno", "deno"))
    with pytest.raises(application.SourceSizeLimitError, match="Source media"):
        application.download_song_from_youtube("query", output_base, "ffmpeg", lambda *_args: None, 100)


def test_source_abort_worker_removes_all_outputs_and_reservations(app, client, monkeypatch):
    upload_csv(app, client)
    app.config.update(MAX_SOURCE_BYTES=5, TASK_BYTE_RESERVATION=10, MAX_JOB_BYTES=100)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    application.job_registry.reserve_indices(job, [0], 1, 10, 100, 1_000)
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def source_abort(_query, output_base, _ffmpeg, _progress, max_source, **_kwargs):
        assert max_source == 5
        output_base.with_suffix(".webm").write_bytes(b"source")
        output_base.with_suffix(".part").write_bytes(b"partial")
        raise application.SourceSizeLimitError("too large")

    monkeypatch.setattr(application, "download_song_from_youtube", source_abort)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), 10)
    assert job.active_count == 0
    assert job.reserved_bytes == 0
    assert job.retained_bytes == 0
    assert job.files == {}
    assert list(job.directory.iterdir()) == []


def test_concurrent_job_slot_limit_is_atomic_before_directory_creation(tmp_path):
    registry = application.JobRegistry()
    barrier = threading.Barrier(3)
    outcomes = []

    def create_one():
        barrier.wait()
        try:
            registry.create(tmp_path, max_jobs=1, max_total_job_bytes=100)
            outcomes.append("created")
        except application.JobCapacityError:
            outcomes.append("full")

    threads = [threading.Thread(target=create_one), threading.Thread(target=create_one)]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["created", "full"]
    assert len(list(tmp_path.iterdir())) == 1


def test_registry_wide_byte_reservation_and_reconciliation_boundaries(tmp_path):
    registry = application.JobRegistry()
    first = registry.create(tmp_path, max_jobs=3, max_total_job_bytes=10)
    second = registry.create(tmp_path, max_jobs=3, max_total_job_bytes=10)
    registry.reserve_indices(first, [0], 1, 6, 100, 10)
    with pytest.raises(application.JobAdmissionError, match="service-wide"):
        registry.reserve_indices(second, [0], 1, 5, 100, 10)
    assert second.active_count == 0 and second.reserved_bytes == 0
    assert registry.retain_artifact(first, 0, "first.mp3", 4, 100, 10)
    registry.release_task(first, 0, 6)
    registry.reserve_indices(second, [0], 1, 6, 100, 10)
    assert first.retained_bytes + second.reserved_bytes == 10
    with pytest.raises(application.JobCapacityError, match="storage capacity"):
        registry.create(tmp_path, max_jobs=3, max_total_job_bytes=10)
    assert len(list(tmp_path.iterdir())) == 2


def test_concurrent_global_byte_admission_has_one_winner(tmp_path):
    registry = application.JobRegistry()
    first = registry.create(tmp_path, max_jobs=2, max_total_job_bytes=10)
    second = registry.create(tmp_path, max_jobs=2, max_total_job_bytes=10)
    barrier = threading.Barrier(3)
    outcomes = []

    def reserve(job):
        barrier.wait()
        try:
            registry.reserve_indices(job, [0], 1, 6, 100, 10)
            outcomes.append("reserved")
        except application.JobAdmissionError:
            outcomes.append("full")

    threads = [threading.Thread(target=reserve, args=(first,)), threading.Thread(target=reserve, args=(second,))]
    for thread in threads:
        thread.start()
    barrier.wait()
    for thread in threads:
        thread.join(timeout=2)
    assert all(not thread.is_alive() for thread in threads)
    assert sorted(outcomes) == ["full", "reserved"]
    assert first.reserved_bytes + second.reserved_bytes == 6


def test_full_job_capacity_returns_clear_503_without_directory(app, tmp_path):
    limited = application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "full-jobs"),
            "RATELIMIT_ENABLED": False,
            "MAX_JOBS": 1,
            "MAX_TOTAL_JOB_BYTES": 100,
            "JOB_TTL_SECONDS": 3_600,
        }
    )
    first = limited.test_client()
    second = limited.test_client()
    assert first.get("/").status_code == 200
    response = second.get("/")
    assert response.status_code == 503
    assert b"capacity" in response.data.lower()
    assert len(list((tmp_path / "full-jobs").iterdir())) == 1


def test_full_global_bytes_returns_clear_json_503_without_directory(tmp_path):
    limited = application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "full-bytes"),
            "RATELIMIT_ENABLED": False,
            "MAX_JOBS": 2,
            "MAX_TOTAL_JOB_BYTES": 5,
        }
    )
    first = limited.test_client()
    assert first.get("/").status_code == 200
    job = current_job(first)
    with job.lock:
        job.retained_bytes = 5
    response = limited.test_client().get("/", headers={"Accept": "application/json"})
    assert response.status_code == 503
    assert "storage capacity" in response.json["error"]
    assert len(list((tmp_path / "full-bytes").iterdir())) == 1


class FakeClock:
    def __init__(self, value=0.0):
        self.value = value

    def __call__(self):
        return self.value


def test_fake_clock_ttl_boundary_skips_active_and_outside_root_jobs(tmp_path):
    clock = FakeClock()
    registry = application.JobRegistry(clock)
    root = tmp_path / "jobs"
    idle = registry.create(root)
    active = registry.create(root)
    pending = registry.create(root)
    outside = registry.create(root)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_marker = outside_dir / "keep"
    outside_marker.write_text("safe")
    outside.directory = outside_dir
    registry.reserve_indices(active, [0], 1, 1, 10, 100)
    registry.enqueue_indices(pending, [0, 1], 1, 1, 10, 100)
    clock.value = 9.9
    assert registry.reap_expired(root, 10) == 0
    clock.value = 10
    assert registry.reap_expired(root, 10) == 1
    assert registry.get(idle.job_id) is None
    assert registry.get(active.job_id) is active
    assert registry.get(pending.job_id) is pending
    assert pending.pending_indices == [1]
    assert registry.get(outside.job_id) is outside
    assert active.directory.exists()
    assert outside_marker.read_text() == "safe"


def test_failed_ttl_reap_reconciles_restores_and_touches_same_job(tmp_path):
    clock = FakeClock()
    registry = application.JobRegistry(clock)
    job = registry.create(tmp_path)
    filename = "retained.mp3"
    (job.directory / filename).write_bytes(b"1234")
    job.files[0] = filename
    job.retained_bytes = 4
    clock.value = 20

    def partial_failure(path):
        (Path(path) / filename).unlink()
        raise OSError("locked")

    assert registry.reap_expired(tmp_path, 10, partial_failure) == 0
    assert registry.get(job.job_id) is job
    assert job.lifecycle == "accepting"
    assert job.files == {} and job.retained_bytes == 0
    assert job.last_activity == 20
    assert job.directory.exists()


def test_ttl_deletion_runs_outside_locks_and_closing_job_retains_slot(tmp_path):
    clock = FakeClock()
    registry = application.JobRegistry(clock)
    job = registry.create(tmp_path, max_jobs=1, max_total_job_bytes=100)
    clock.value = 20
    entered = threading.Event()
    release = threading.Event()

    def blocked_delete(path):
        entered.set()
        assert release.wait(timeout=2)
        application.shutil.rmtree(path)

    reaper = threading.Thread(target=lambda: registry.reap_expired(tmp_path, 10, blocked_delete))
    reaper.start()
    assert entered.wait(timeout=2)
    outcome = []

    def attempt_create():
        try:
            registry.create(tmp_path, max_jobs=1, max_total_job_bytes=100)
            outcome.append("created")
        except application.JobCapacityError:
            outcome.append("full")

    admission = threading.Thread(target=attempt_create)
    admission.start()
    admission.join(timeout=1)
    try:
        assert not admission.is_alive()
        assert outcome == ["full"]
        assert registry.get(job.job_id) is job
        assert job.lifecycle == "closing"
    finally:
        release.set()
        admission.join(timeout=2)
        reaper.join(timeout=2)
    assert not reaper.is_alive()
    assert registry.get(job.job_id) is None


def test_http_requests_opportunistically_reap_only_after_last_activity(tmp_path, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(application.job_registry, "_clock", clock)
    expiring = application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "opportunistic"),
            "RATELIMIT_ENABLED": False,
            "MAX_JOBS": 1,
            "MAX_TOTAL_JOB_BYTES": 100,
            "JOB_TTL_SECONDS": 10,
        }
    )
    owner = expiring.test_client()
    newcomer = expiring.test_client()
    assert owner.get("/").status_code == 200
    clock.value = 5
    assert owner.get("/").status_code == 200
    clock.value = 14
    assert newcomer.get("/").status_code == 503
    clock.value = 15
    assert newcomer.get("/").status_code == 200
    assert len(list((tmp_path / "opportunistic").iterdir())) == 1


def test_python_dotenv_security_pin_is_current():
    requirements = Path("requirements.txt").read_text(encoding="utf-8")
    assert "python-dotenv==1.2.2" in requirements
    assert "python-dotenv==1.1.1" not in requirements


def constrained_capacity_app(tmp_path):
    return application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "capacity-jobs"),
            "RATELIMIT_ENABLED": False,
            "MAX_JOBS": 1,
            "MAX_TOTAL_JOB_BYTES": 5,
            "MAX_JOB_BYTES": 5,
            "TASK_BYTE_RESERVATION": 5,
            "JOB_TTL_SECONDS": 3_600,
        }
    )


def seed_five_byte_job(app, client):
    assert client.get("/").status_code == 200
    job = current_job(client)
    filename = "retained.mp3"
    (job.directory / filename).write_bytes(b"12345")
    job.files[0] = filename
    job.retained_bytes = 5
    return job


def test_direct_manual_close_holds_slot_and_bytes_until_atomic_replacement(tmp_path):
    registry = application.JobRegistry()
    root = tmp_path / "direct"
    job = registry.create(root, max_jobs=1, max_total_job_bytes=5)
    (job.directory / "retained.mp3").write_bytes(b"12345")
    job.files[0] = "retained.mp3"
    job.retained_bytes = 5
    registry.close_if_idle(job)
    assert registry.get(job.job_id) is job
    assert job.lifecycle == "closing"
    with pytest.raises(application.JobCapacityError, match="active-job"):
        registry.create(root, max_jobs=1, max_total_job_bytes=5)
    with pytest.raises(application.JobUnavailableError):
        registry.reserve_indices(job, [0], 1, 1, 5, 5)
    application.shutil.rmtree(job.directory)
    replacement = registry.replace_closing(job, root, [{"Song": "New", "Artist": "Artist"}])
    assert registry.get(job.job_id) is None
    assert registry.get(replacement.job_id) is replacement
    assert replacement.job_id != job.job_id
    assert replacement.songs[0]["Song"] == "New"
    assert replacement.retained_bytes == 0 and replacement.reserved_bytes == 0
    assert len(registry._jobs) == 1
    assert len(list(root.iterdir())) == 1


def test_cleanup_paused_deletion_holds_capacity_then_replaces_atomically(tmp_path, monkeypatch):
    limited = constrained_capacity_app(tmp_path)
    owner = limited.test_client()
    newcomer = limited.test_client()
    job = seed_five_byte_job(limited, owner)
    token = csrf_for(limited, owner)
    entered = threading.Event()
    release = threading.Event()
    real_rmtree = application.shutil.rmtree

    def paused_delete(path):
        entered.set()
        assert release.wait(timeout=3)
        real_rmtree(path)

    monkeypatch.setattr(application.shutil, "rmtree", paused_delete)
    responses = []
    worker = threading.Thread(
        target=lambda: responses.append(owner.post("/cleanup", json={}, headers={"X-CSRFToken": token}))
    )
    worker.start()
    assert entered.wait(timeout=2)
    try:
        assert application.job_registry.get(job.job_id) is job
        assert job.lifecycle == "closing" and job.retained_bytes == 5
        assert len(application.job_registry._jobs) == 1
        assert newcomer.get("/").status_code == 503
        assert len(list((tmp_path / "capacity-jobs").iterdir())) == 1
    finally:
        release.set()
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert responses[0].status_code == 200
    replacement = current_job(owner)
    assert replacement.job_id != job.job_id
    assert replacement.lifecycle == "accepting"
    assert replacement.retained_bytes == 0 and replacement.reserved_bytes == 0
    assert len(application.job_registry._jobs) == 1
    assert len(list((tmp_path / "capacity-jobs").iterdir())) == 1


def test_upload_paused_deletion_holds_capacity_then_replaces_with_songs(tmp_path, monkeypatch):
    limited = constrained_capacity_app(tmp_path)
    owner = limited.test_client()
    newcomer = limited.test_client()
    job = seed_five_byte_job(limited, owner)
    token = csrf_for(limited, owner)
    entered = threading.Event()
    release = threading.Event()
    real_rmtree = application.shutil.rmtree

    def paused_delete(path):
        entered.set()
        assert release.wait(timeout=3)
        real_rmtree(path)

    monkeypatch.setattr(application.shutil, "rmtree", paused_delete)
    responses = []

    def post_upload():
        responses.append(
            owner.post(
                "/upload",
                data={
                    "csrf_token": token,
                    "csv_file": (io.BytesIO(b"Song,Artist\nReplacement,Performer\n"), "replacement.csv"),
                },
                content_type="multipart/form-data",
            )
        )

    worker = threading.Thread(target=post_upload)
    worker.start()
    assert entered.wait(timeout=2)
    try:
        assert application.job_registry.get(job.job_id) is job
        assert job.lifecycle == "closing" and job.retained_bytes == 5
        assert newcomer.get("/").status_code == 503
        assert len(list((tmp_path / "capacity-jobs").iterdir())) == 1
    finally:
        release.set()
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert responses[0].status_code == 200
    replacement = current_job(owner)
    assert replacement.job_id != job.job_id
    assert replacement.songs[0]["Song"] == "Replacement"
    assert replacement.retained_bytes == 0
    assert len(application.job_registry._jobs) == 1
    assert len(list((tmp_path / "capacity-jobs").iterdir())) == 1


def test_cleanup_failed_deletion_never_releases_capacity_and_restores_exact_accounting(tmp_path, monkeypatch):
    limited = constrained_capacity_app(tmp_path)
    owner = limited.test_client()
    newcomer = limited.test_client()
    job = seed_five_byte_job(limited, owner)
    token = csrf_for(limited, owner)
    entered = threading.Event()
    release = threading.Event()

    def paused_failure(_path):
        entered.set()
        assert release.wait(timeout=3)
        raise OSError("locked")

    monkeypatch.setattr(application.shutil, "rmtree", paused_failure)
    responses = []
    worker = threading.Thread(
        target=lambda: responses.append(owner.post("/cleanup", json={}, headers={"X-CSRFToken": token}))
    )
    worker.start()
    assert entered.wait(timeout=2)
    try:
        assert newcomer.get("/").status_code == 503
        assert application.job_registry.get(job.job_id) is job
        assert job.lifecycle == "closing" and job.retained_bytes == 5
        assert len(application.job_registry._jobs) == 1
    finally:
        release.set()
        worker.join(timeout=3)
    assert not worker.is_alive()
    assert responses[0].status_code == 500
    assert application.job_registry.get(job.job_id) is job
    assert job.lifecycle == "accepting"
    assert job.retained_bytes == 5 and job.reserved_bytes == 0
    assert len(application.job_registry._jobs) == 1
    assert len(list((tmp_path / "capacity-jobs").iterdir())) == 1
    with pytest.raises(application.JobCapacityError, match="active-job"):
        application.job_registry.create(
            Path(limited.config["DATA_ROOT"]), max_jobs=1, max_total_job_bytes=5
        )


def test_cleanup_replacement_allocation_failure_restores_coherent_job(tmp_path, monkeypatch):
    limited = constrained_capacity_app(tmp_path)
    owner = limited.test_client()
    job = seed_five_byte_job(limited, owner)
    old_directory = job.directory
    real_mkdir = Path.mkdir

    def fail_only_new_job_directory(path, *args, **kwargs):
        if path.parent == old_directory.parent and path.name != old_directory.name:
            raise OSError("allocation failed")
        return real_mkdir(path, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", fail_only_new_job_directory)
    response = owner.post("/cleanup", json={}, headers={"X-CSRFToken": csrf_for(limited, owner)})
    assert response.status_code == 500
    assert application.job_registry.get(job.job_id) is job
    assert job.lifecycle == "accepting"
    assert job.directory.exists()
    assert job.files == {} and job.retained_bytes == 0 and job.reserved_bytes == 0
    assert len(application.job_registry._jobs) == 1
    assert len(list((tmp_path / "capacity-jobs").iterdir())) == 1
