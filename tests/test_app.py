from __future__ import annotations

import io
import os
import threading
from pathlib import Path

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


def test_valid_upload_renders_and_cookie_session_contains_only_job_id(app, client):
    response = upload_csv(app, client)
    assert response.status_code == 200
    assert b"Halo" in response.data
    assert b"loop.index" not in response.data
    with client.session_transaction() as flask_session:
        assert list(flask_session.keys()) == ["job_id"]


def test_render_includes_accessibility_and_local_ui_contract(app, client):
    response = client.get("/")
    assert response.status_code == 200
    assert b'class="skip-link"' in response.data
    assert b'aria-live="polite"' in response.data
    assert b'id="drop-zone"' in response.data
    assert b"toastify" not in response.data.lower()
    css = Path("static/style.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


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

    def fake_download(_query, output_base, _ffmpeg, progress, _max_source):
        progress(None, "Still working")
        output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "download_song_from_youtube", fake_download)
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    application.process_song(app, sio, job.job_id, 0, dict(job.songs[0]), reservation)
    assert job.active_count == 0
    assert job.reserved_bytes == 0
    assert job.retained_bytes == 5
    assert job.files[0].endswith(".mp3")
    assert all(item[2]["to"] == application.job_room(job.job_id) for item in emitted)
    assert emitted[-1][1]["download_url"].startswith(f"/jobs/{job.job_id}/files/")


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


def test_whole_request_task_ceiling_rejects_before_spawn(app, client, monkeypatch):
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
    assert response.status_code == 409
    assert "at most 1" in response.json["error"]
    assert calls == []
    assert job.active_count == 0
    assert job.reserved_bytes == 0


def test_cumulative_budget_blocks_second_artifact_before_spawn(app, client, monkeypatch):
    upload_csv(app, client, "Song,Artist\nA,B\nC,D\n")
    app.config.update(TASK_BYTE_RESERVATION=6, MAX_JOB_BYTES=10, MAX_ARTIFACT_BYTES=10)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_six(_query, output_base, _ffmpeg, _progress, _max_source):
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
    app.config.update(TASK_BYTE_RESERVATION=4, MAX_JOB_BYTES=5, MAX_ARTIFACT_BYTES=10)
    job = current_job(client)
    sio = app.extensions["socketio_instance"]
    monkeypatch.setattr(application, "resolve_ffmpeg", lambda value=None: "ffmpeg")
    monkeypatch.setattr(application, "tag_mp3_file", lambda *args: None)
    monkeypatch.setattr(sio, "emit", lambda *args, **kwargs: None)

    def write_six(_query, output_base, _ffmpeg, _progress, _max_source):
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

    def fail_after_partial(_query, output_base, _ffmpeg, _progress, _max_source):
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
            output_base.with_suffix(".mp3").write_bytes(b"audio")

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
    application.download_song_from_youtube("query", output_base, "ffmpeg", lambda *_args: None, 100)
    assert captured["max_filesize"] == 100


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

    monkeypatch.setattr(application, "YoutubeDL", FakeYDL)
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

    def source_abort(_query, output_base, _ffmpeg, _progress, max_source):
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
    outside = registry.create(root)
    outside_dir = tmp_path / "outside"
    outside_dir.mkdir()
    outside_marker = outside_dir / "keep"
    outside_marker.write_text("safe")
    outside.directory = outside_dir
    registry.reserve_indices(active, [0], 1, 1, 10, 100)
    clock.value = 9.9
    assert registry.reap_expired(root, 10) == 0
    clock.value = 10
    assert registry.reap_expired(root, 10) == 1
    assert registry.get(idle.job_id) is None
    assert registry.get(active.job_id) is active
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
