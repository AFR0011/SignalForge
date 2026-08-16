from __future__ import annotations

import pytest

import app as application


@pytest.fixture(autouse=True)
def clear_registry():
    application.job_registry.clear()
    yield
    application.job_registry.clear()


@pytest.fixture(autouse=True)
def isolate_default_library_root(tmp_path, monkeypatch):
    monkeypatch.setattr(
        application, "default_library_root", lambda: tmp_path / "default-library"
    )


@pytest.fixture
def app(tmp_path):
    return application.create_app(
        {
            "TESTING": True,
            "SECRET_KEY": "test-secret-that-is-longer-than-thirty-two-characters",
            "PRODUCTION": False,
            "DATA_ROOT": str(tmp_path / "jobs"),
            "LIBRARY_ROOT": str(tmp_path / "library"),
            "RATELIMIT_ENABLED": False,
            "CSV_MAX_BYTES": 512,
            "CSV_MAX_ROWS": 3,
            "CSV_MAX_FIELD_LENGTH": 40,
            "SELECTION_LIMIT": 2,
            "ZIP_MAX_BYTES": 64,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


def current_job(client):
    with client.session_transaction() as flask_session:
        job_id = flask_session["job_id"]
    return application.job_registry.get(job_id)


def csrf_for(app, client):
    job = current_job(client)
    return application._csrf_token(app, job.job_id)


def upload_csv(app, client, csv_text="Song,Artist,Album,Genres\nHalo,Starling,Blue,Pop\n"):
    import io

    client.get("/")
    return client.post(
        "/upload",
        data={
            "csrf_token": csrf_for(app, client),
            "csv_file": (io.BytesIO(csv_text.encode()), "tracks.csv"),
        },
        content_type="multipart/form-data",
    )
