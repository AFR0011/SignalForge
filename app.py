"""Secure single-process CSV-to-MP3 web application.

Jobs and rate limits are intentionally process-local. Production must run exactly
one worker; see Procfile and README.md.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import logging
import os
import re
import secrets
import shutil
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse
from urllib.parse import quote

import imageio_ffmpeg
import requests
from dotenv import load_dotenv
from flask import (
    Flask,
    after_this_request,
    jsonify,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO, emit, join_room
from mutagen.easyid3 import EasyID3
from mutagen.id3 import APIC, ID3, error
from mutagen.mp3 import MP3
from werkzeug.exceptions import HTTPException, RequestEntityTooLarge
from yt_dlp import DownloadError, YoutubeDL


LOGGER = logging.getLogger(__name__)
JOB_ID_RE = re.compile(r"^[A-Za-z0-9_-]{32,128}$")
SAFE_FILENAME_RE = re.compile(r"[^A-Za-z0-9._-]+")
SECRET_PLACEHOLDERS = {
    "change-me",
    "changeme",
    "dev-secret",
    "dev-secret-change-me",
    "replace-me",
    "secret",
    "your-secret-key",
}


@dataclass
class Job:
    job_id: str
    directory: Path
    songs: tuple[dict[str, str], ...] = ()
    statuses: dict[int, dict[str, Any]] = field(default_factory=dict)
    files: dict[int, str] = field(default_factory=dict)
    failed: set[int] = field(default_factory=set)
    lifecycle: str = "accepting"
    active_count: int = 0
    reserved_bytes: int = 0
    retained_bytes: int = 0
    reserved_indices: set[int] = field(default_factory=set)
    active_indices: set[int] = field(default_factory=set)
    reservation_sizes: dict[int, int] = field(default_factory=dict)
    last_activity: float = 0.0
    lock: threading.RLock = field(default_factory=threading.RLock, repr=False)


class JobAdmissionError(RuntimeError):
    """Raised when a whole admission request cannot be reserved safely."""


class JobBusyError(RuntimeError):
    """Raised when a job cannot transition to closing while work is reserved."""


class JobUnavailableError(RuntimeError):
    """Raised when a job is no longer the accepting registry entry."""


class JobCapacityError(RuntimeError):
    """Raised before allocation when process-wide capacity is exhausted."""


class SourceSizeLimitError(RuntimeError):
    """Raised when yt-dlp reports source bytes above the configured cap."""


class JobRegistry:
    """Thread-safe process-local registry for opaque jobs."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._clock = clock

    def now(self) -> float:
        return float(self._clock())

    def _total_bytes_locked(self) -> int:
        total = 0
        for current in sorted(self._jobs.values(), key=lambda item: item.job_id):
            with current.lock:
                total += current.retained_bytes + current.reserved_bytes
        return total

    def create(
        self,
        data_root: Path,
        songs: list[dict[str, str]] | None = None,
        max_jobs: int = 100,
        max_total_job_bytes: int = 2_000_000_000,
    ) -> Job:
        data_root.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if len(self._jobs) >= max_jobs:
                raise JobCapacityError("The service has reached its active-job capacity")
            if self._total_bytes_locked() >= max_total_job_bytes:
                raise JobCapacityError("The service has reached its total job-storage capacity")
            for _ in range(10):
                job_id = secrets.token_urlsafe(32)
                if job_id in self._jobs:
                    continue
                directory = data_root / job_id
                job = Job(
                    job_id=job_id,
                    directory=directory,
                    songs=tuple(songs or ()),
                    last_activity=self.now(),
                )
                try:
                    directory.mkdir(mode=0o700)
                except FileExistsError:
                    continue
                try:
                    self._jobs[job_id] = job
                except Exception:
                    directory.rmdir()
                    raise
                return job
        raise RuntimeError("Unable to allocate a unique job")

    def get(self, job_id: str | None, touch: bool = False) -> Job | None:
        if not job_id:
            return None
        with self._lock:
            job = self._jobs.get(job_id)
            if job is not None and touch:
                with job.lock:
                    if job.lifecycle == "accepting":
                        job.last_activity = self.now()
            return job

    def touch(self, job: Job) -> None:
        with self._lock:
            with job.lock:
                if self._jobs.get(job.job_id) is job and job.lifecycle == "accepting":
                    job.last_activity = self.now()

    def reserve_indices(
        self,
        job: Job,
        indices: list[int],
        task_limit: int,
        reservation_bytes: int,
        job_byte_limit: int,
        total_byte_limit: int | None = None,
    ) -> list[int]:
        """Atomically reserve a whole admission request before threads exist."""
        with self._lock:
            process_total = self._total_bytes_locked()
            with job.lock:
                if self._jobs.get(job.job_id) is not job or job.lifecycle != "accepting":
                    raise JobUnavailableError("Job is closing; refresh before starting more work")
                candidates = [
                    index
                    for index in indices
                    if index not in job.reserved_indices
                    and job.statuses.get(index, {}).get("status") not in {"success"}
                ]
                if job.active_count + len(candidates) > task_limit:
                    raise JobAdmissionError(
                        f"This job allows at most {task_limit} queued or active tasks"
                    )
                requested_bytes = reservation_bytes * len(candidates)
                if job.retained_bytes + job.reserved_bytes + requested_bytes > job_byte_limit:
                    raise JobAdmissionError("This request exceeds the remaining per-job disk budget")
                if total_byte_limit is not None and process_total + requested_bytes > total_byte_limit:
                    raise JobAdmissionError("This request exceeds the remaining service-wide disk budget")
                for index in candidates:
                    job.active_count += 1
                    job.reserved_bytes += reservation_bytes
                    job.reserved_indices.add(index)
                    job.active_indices.add(index)
                    job.reservation_sizes[index] = reservation_bytes
                    job.statuses[index] = {
                        "job_id": job.job_id,
                        "index": index,
                        "status": "queued",
                        "message": "Queued",
                    }
                if candidates:
                    job.last_activity = self.now()
                return candidates

    def release_task(
        self,
        job: Job,
        index: int,
        reservation_bytes: int,
        failure_message: str | None = None,
    ) -> None:
        """Release exactly one pre-spawn reservation without underflow."""
        with self._lock:
            with job.lock:
                if self._jobs.get(job.job_id) is not job or index not in job.reserved_indices:
                    if index not in job.active_indices:
                        return
                if index in job.reserved_indices:
                    job.reserved_indices.remove(index)
                    reserved = job.reservation_sizes.pop(index, reservation_bytes)
                    job.reserved_bytes = max(0, job.reserved_bytes - reserved)
                if index in job.active_indices:
                    job.active_indices.remove(index)
                    job.active_count = max(0, job.active_count - 1)
                if failure_message:
                    job.failed.add(index)
                    job.statuses[index] = {
                        "job_id": job.job_id,
                        "index": index,
                        "status": "failed",
                        "message": failure_message,
                    }
                job.last_activity = self.now()

    def retain_artifact(
        self,
        job: Job,
        index: int,
        filename: str,
        actual_bytes: int,
        job_byte_limit: int,
        total_byte_limit: int | None = None,
    ) -> bool:
        """Atomically reconcile actual bytes before exposing an artifact."""
        with self._lock:
            process_total = self._total_bytes_locked()
            with job.lock:
                if (
                    self._jobs.get(job.job_id) is not job
                    or job.lifecycle != "accepting"
                    or index not in job.reserved_indices
                ):
                    return False
                reservation = job.reservation_sizes.get(index, 0)
                if job.retained_bytes + job.reserved_bytes - reservation + actual_bytes > job_byte_limit:
                    return False
                if (
                    total_byte_limit is not None
                    and process_total - reservation + actual_bytes > total_byte_limit
                ):
                    return False
                job.reserved_indices.remove(index)
                job.reservation_sizes.pop(index, None)
                job.reserved_bytes = max(0, job.reserved_bytes - reservation)
                job.retained_bytes += actual_bytes
                job.files[index] = filename
                job.failed.discard(index)
                job.last_activity = self.now()
                return True

    def close_if_idle(self, job: Job) -> Job:
        """Atomically stop admission while retaining all global capacity."""
        with self._lock:
            with job.lock:
                if self._jobs.get(job.job_id) is not job or job.lifecycle != "accepting":
                    raise JobUnavailableError("Job is already closing or unavailable")
                if job.active_count or job.reserved_bytes or job.reserved_indices or job.active_indices:
                    raise JobBusyError("Cannot clear a job with queued or active work")
                job.lifecycle = "closing"
                return job

    def replace_closing(
        self,
        job: Job,
        data_root: Path,
        songs: list[dict[str, str]] | None = None,
    ) -> Job:
        """Allocate and atomically swap a closing entry without freeing its slot."""
        root = data_root.resolve()
        with self._lock:
            with job.lock:
                if self._jobs.get(job.job_id) is not job or job.lifecycle != "closing":
                    raise JobUnavailableError("Job is not available for replacement")
                if job.active_count or job.reserved_bytes or job.reserved_indices or job.active_indices:
                    raise JobBusyError("Cannot replace a job with queued or active work")
                for _ in range(10):
                    job_id = secrets.token_urlsafe(32)
                    if job_id in self._jobs:
                        continue
                    directory = root / job_id
                    replacement = Job(
                        job_id=job_id,
                        directory=directory,
                        songs=tuple(songs or ()),
                        last_activity=self.now(),
                    )
                    try:
                        directory.mkdir(mode=0o700)
                    except FileExistsError:
                        continue
                    try:
                        self._jobs[job_id] = replacement
                    except Exception:
                        directory.rmdir()
                        raise
                    self._jobs.pop(job.job_id)
                    return replacement
        raise RuntimeError("Unable to allocate a unique replacement job")

    def finalize_closing(self, job: Job) -> bool:
        """Remove a capacity-bearing closing entry after successful deletion."""
        with self._lock:
            with job.lock:
                if self._jobs.get(job.job_id) is not job or job.lifecycle != "closing":
                    return False
                if job.active_count or job.reserved_bytes or job.reserved_indices or job.active_indices:
                    return False
                self._jobs.pop(job.job_id)
                return True

    def restore(self, job: Job) -> None:
        """Restore an accepting registry entry after filesystem deletion fails."""
        with self._lock:
            with job.lock:
                existing = self._jobs.get(job.job_id)
                if existing is not None and existing is not job:
                    raise RuntimeError("Cannot restore job because its identifier is already in use")
                job.lifecycle = "accepting"
                job.last_activity = self.now()
                self._jobs[job.job_id] = job

    def reap_expired(
        self,
        data_root: Path,
        ttl_seconds: float,
        delete_directory: Callable[[Path], Any] | None = None,
    ) -> int:
        """Claim expired idle jobs atomically, then delete outside all locks."""
        delete = delete_directory or shutil.rmtree
        root = data_root.resolve()
        now = self.now()
        claimed: list[tuple[Job, Path]] = []
        with self._lock:
            for job in sorted(self._jobs.values(), key=lambda item: item.job_id):
                with job.lock:
                    if (
                        job.lifecycle != "accepting"
                        or job.active_count
                        or job.reserved_bytes
                        or job.reserved_indices
                        or job.active_indices
                        or now - job.last_activity < ttl_seconds
                    ):
                        continue
                    try:
                        directory = safe_job_directory(root, job.job_id, job.directory)
                    except ValueError:
                        continue
                    job.lifecycle = "closing"
                    claimed.append((job, directory))

        removed = 0
        for job, directory in claimed:
            try:
                if directory.exists():
                    delete(directory)
            except Exception:
                try:
                    reconcile_job_storage(job, root)
                except (OSError, ValueError):
                    LOGGER.exception("Could not fully reconcile expired job storage")
                self.restore(job)
                continue
            if self.finalize_closing(job):
                removed += 1
        return removed

    def clear(self) -> None:
        with self._lock:
            self._jobs.clear()


job_registry = JobRegistry()


def is_strong_secret(value: str | None) -> bool:
    if not value or len(value.strip()) < 32:
        return False
    normalized = value.strip().lower()
    if normalized in SECRET_PLACEHOLDERS:
        return False
    return (
        len(set(normalized)) >= 4
        and not any(marker in normalized for marker in ("change-me", "replace-me", "placeholder"))
    )


def _production_requested(config: dict[str, Any] | None = None) -> bool:
    if config and "PRODUCTION" in config:
        return bool(config["PRODUCTION"])
    return bool(
        os.environ.get("RENDER")
        or os.environ.get("RENDER_EXTERNAL_URL")
        or os.environ.get("APP_ENV", "").lower() == "production"
        or os.environ.get("FLASK_ENV", "").lower() == "production"
    )


def _configure_secret(app: Flask, supplied_config: dict[str, Any] | None) -> None:
    production = _production_requested(supplied_config)
    configured = (
        supplied_config.get("SECRET_KEY")
        if supplied_config is not None and "SECRET_KEY" in supplied_config
        else (app.config.get("SECRET_KEY") or os.environ.get("SECRET_KEY"))
    )
    if production and not is_strong_secret(configured):
        raise RuntimeError("Production requires a strong SECRET_KEY of at least 32 characters")
    if not configured:
        configured = secrets.token_urlsafe(48)
        LOGGER.warning(
            "SECRET_KEY is not configured; using an ephemeral development key. "
            "Sessions will reset when the process restarts."
        )
    elif not is_strong_secret(str(configured)):
        LOGGER.warning("Development SECRET_KEY is weak; never use it in production")
    app.config["SECRET_KEY"] = configured
    app.config["PRODUCTION"] = production


def safe_job_directory(data_root: Path, job_id: str, candidate: Path | None = None) -> Path:
    if not JOB_ID_RE.fullmatch(job_id):
        raise ValueError("Invalid job identifier")
    root = data_root.resolve()
    path = (candidate or (root / job_id)).resolve()
    if path.parent != root or path.name != job_id:
        raise ValueError("Job directory is outside DATA_ROOT")
    return path


def safe_artifact_path(job: Job, filename: str, data_root: Path | None = None) -> Path:
    if not filename or filename != Path(filename).name:
        raise ValueError("Invalid filename")
    if data_root is not None:
        safe_job_directory(data_root, job.job_id, job.directory)
    path = (job.directory / filename).resolve()
    if path.parent != job.directory.resolve():
        raise ValueError("Artifact is outside the job directory")
    return path


def reconcile_job_storage(job: Job, data_root: Path) -> None:
    """Rebuild retained accounting after a potentially partial failed deletion."""
    directory = safe_job_directory(data_root, job.job_id, job.directory)
    directory.mkdir(mode=0o700, exist_ok=True)
    retained = 0
    surviving: dict[int, str] = {}
    with job.lock:
        for index, filename in job.files.items():
            try:
                path = safe_artifact_path(job, filename, data_root)
                if path.is_file():
                    retained += path.stat().st_size
                    surviving[index] = filename
            except (OSError, ValueError):
                continue
        job.files = surviving
        job.retained_bytes = retained


def deterministic_filename(index: int, song: dict[str, str]) -> str:
    title = format_title(song.get("Song", ""))
    artist = sanitize_metadata_field(song.get("Artist", ""))
    stem = SAFE_FILENAME_RE.sub("-", f"{title}-{artist}").strip("-._").lower()
    stem = stem[:96] or "track"
    return f"{index + 1:04d}-{stem}.mp3"


def parse_csv_upload(file_storage: Any, config: dict[str, Any]) -> list[dict[str, str]]:
    if not file_storage or not file_storage.filename:
        raise ValueError("Choose a CSV file to upload")
    if Path(file_storage.filename).suffix.lower() != ".csv":
        raise ValueError("The uploaded file must use the .csv extension")

    byte_limit = int(config["CSV_MAX_BYTES"])
    raw = file_storage.stream.read(byte_limit + 1)
    if len(raw) > byte_limit:
        raise ValueError(f"CSV exceeds the {byte_limit}-byte limit")
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    try:
        reader = csv.DictReader(text.splitlines(), strict=True)
        headers = reader.fieldnames
        if not headers:
            raise ValueError("CSV must include a header row")
        headers = [header.strip() if header is not None else "" for header in headers]
        if not all(headers) or len(set(headers)) != len(headers):
            raise ValueError("CSV headers must be non-empty and unique")
        if not {"Song", "Artist"}.issubset(headers):
            raise ValueError("CSV must include Song and Artist columns")

        rows: list[dict[str, str]] = []
        field_limit = int(config["CSV_MAX_FIELD_LENGTH"])
        row_limit = int(config["CSV_MAX_ROWS"])
        for row_number, raw_row in enumerate(reader, start=2):
            if len(rows) >= row_limit:
                raise ValueError(f"CSV exceeds the {row_limit}-row limit")
            if None in raw_row:
                raise ValueError(f"Row {row_number} has too many fields")
            clean: dict[str, str] = {}
            for key in ("Song", "Artist", "Album", "Genres"):
                value = sanitize_metadata_field(raw_row.get(key, ""))
                if len(value) > field_limit:
                    raise ValueError(f"Row {row_number} contains a field longer than {field_limit} characters")
                clean[key] = value
            if not clean["Song"] or not clean["Artist"]:
                raise ValueError(f"Row {row_number} requires both Song and Artist")
            rows.append(clean)
    except csv.Error as exc:
        raise ValueError("CSV is malformed") from exc

    if not rows:
        raise ValueError("CSV does not contain any songs")
    return rows


def validate_selection(values: Any, song_count: int, limit: int) -> list[int]:
    if not isinstance(values, list) or not values:
        raise ValueError("Select at least one song")
    if len(values) > limit:
        raise ValueError(f"Select no more than {limit} songs")
    indices: list[int] = []
    for value in values:
        if isinstance(value, bool):
            raise ValueError("Selection contains an invalid index")
        try:
            index = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Selection contains an invalid index") from exc
        if str(value).strip() != str(index):
            raise ValueError("Selection contains an invalid index")
        if index < 0 or index >= song_count:
            raise ValueError("Selection contains an out-of-range index")
        indices.append(index)
    if len(indices) != len(set(indices)):
        raise ValueError("Selection contains duplicate indices")
    return indices


def sanitize_metadata_field(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def format_title(raw_title: str) -> str:
    title = sanitize_metadata_field(raw_title)
    title = re.sub(r"\s*\((?:feat|ft)\.?[^)]*\)", "", title, flags=re.I)
    title = re.sub(r"\s?[_-]+\s?", " ", title)
    if re.search(r"\bslowed\b", title, flags=re.I):
        title = re.sub(r"\s*(slowed|slowed remix)[^)]*$", "", title, flags=re.I).strip() + " (Slowed)"
    elif re.search(r"\b(sped up|speed up|speedup|speed-up)\b", title, flags=re.I):
        title = re.sub(r"\s*(sped up|speed up|speedup|speed-up)[^)]*$", "", title, flags=re.I).strip() + " (Sped Up)"
    title = title.lower().title()
    return re.sub(r"('(S|T))\b", lambda match: match.group(1).lower(), title)


def resolve_ffmpeg(configured_path: str | None = None) -> str:
    override = configured_path or os.environ.get("FFMPEG_PATH")
    if override:
        path = Path(override).expanduser().resolve()
        if not path.is_file() or not os.access(path, os.X_OK):
            raise RuntimeError("FFMPEG_PATH must reference an executable file")
        return str(path)
    fallback = Path(imageio_ffmpeg.get_ffmpeg_exe()).resolve()
    if not fallback.is_file():
        raise RuntimeError("Bundled FFmpeg executable was not found")
    return str(fallback)


def _read_limited_response(response: requests.Response, maximum: int) -> bytes:
    length = response.headers.get("Content-Length")
    if length:
        try:
            if int(length) > maximum:
                raise ValueError("Remote response is too large")
        except ValueError as exc:
            if str(exc) == "Remote response is too large":
                raise
    chunks = bytearray()
    for chunk in response.iter_content(64 * 1024):
        chunks.extend(chunk)
        if len(chunks) > maximum:
            raise ValueError("Remote response is too large")
    return bytes(chunks)


def fetch_cover_art(song_title: str, artist_name: str, max_bytes: int = 5_000_000) -> bytes | None:
    try:
        search = requests.get(
            "https://itunes.apple.com/search",
            params={"term": f"{song_title} {artist_name}".strip(), "entity": "song", "limit": 1},
            timeout=(3.05, 8),
        )
        search.raise_for_status()
        if "application/json" not in search.headers.get("Content-Type", "").lower():
            return None
        if len(search.content) > 1_000_000:
            return None
        results = search.json().get("results", [])
        artwork_url = results[0].get("artworkUrl100") if results else None
        if not artwork_url or urlparse(artwork_url).scheme != "https":
            return None
        artwork_url = artwork_url.replace("100x100", "600x600")
        image = requests.get(artwork_url, timeout=(3.05, 8), stream=True)
        image.raise_for_status()
        if not image.headers.get("Content-Type", "").lower().startswith("image/"):
            return None
        return _read_limited_response(image, max_bytes)
    except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
        LOGGER.info("Cover artwork unavailable: %s", exc)
        return None


def tag_mp3_file(filepath: Path, song: dict[str, str], artwork_max_bytes: int) -> None:
    if not filepath.is_file():
        raise FileNotFoundError("Downloaded audio file was not created")
    try:
        audio = EasyID3(str(filepath))
    except Exception:
        audio = MP3(str(filepath), ID3=EasyID3)
        audio.add_tags()
    audio["title"] = format_title(song["Song"])
    audio["artist"] = song["Artist"]
    if song.get("Album"):
        audio["album"] = song["Album"]
    if song.get("Genres"):
        audio["genre"] = [genre.strip() for genre in song["Genres"].split(",") if genre.strip()]
    audio.save()

    cover = fetch_cover_art(song["Song"], song["Artist"].split(",")[0], artwork_max_bytes)
    if cover:
        try:
            tagged = MP3(str(filepath), ID3=ID3)
            if tagged.tags is None:
                tagged.add_tags()
            tagged.tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
            tagged.save()
        except error as exc:
            LOGGER.info("Could not embed artwork: %s", exc)


def download_song_from_youtube(
    query: str,
    output_base: Path,
    ffmpeg_path: str,
    progress: Callable[[float | None, str], None],
    max_source_bytes: int,
) -> None:
    def progress_hook(data: dict[str, Any]) -> None:
        for key in ("total_bytes", "total_bytes_estimate", "downloaded_bytes"):
            measured = data.get(key)
            if isinstance(measured, (int, float)) and not isinstance(measured, bool) and measured > max_source_bytes:
                raise SourceSizeLimitError("Source media exceeds the configured byte limit")
        status = data.get("status")
        if status == "downloading":
            downloaded = data.get("downloaded_bytes")
            total = data.get("total_bytes") or data.get("total_bytes_estimate")
            percent = None
            if isinstance(downloaded, (int, float)) and isinstance(total, (int, float)) and total > 0:
                percent = max(0.0, min(100.0, downloaded / total * 100))
            progress(percent, "Downloading audio")
        elif status == "finished":
            progress(100.0, "Converting and tagging")

    options = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_base}.%(ext)s",
        "ffmpeg_location": ffmpeg_path,
        "max_filesize": max_source_bytes,
        "progress_hooks": [progress_hook],
        "postprocessors": [{"key": "FFmpegExtractAudio", "preferredcodec": "mp3", "preferredquality": "192"}],
        "noplaylist": True,
        "quiet": True,
        "retries": 3,
        "socket_timeout": 30,
    }
    try:
        with YoutubeDL(options) as downloader:
            downloader.download([f"ytsearch1:{query}"])
    except DownloadError:
        raise
    if not output_base.with_suffix(".mp3").is_file():
        raise FileNotFoundError("Download did not produce an MP3 file")


def job_room(job_id: str) -> str:
    return f"job:{job_id}"


def _remove_task_outputs(output_base: Path | None) -> None:
    if output_base is None:
        return
    parent = output_base.parent.resolve()
    for candidate in output_base.parent.glob(f"{output_base.name}.*"):
        try:
            if candidate.resolve().parent == parent and (candidate.is_file() or candidate.is_symlink()):
                candidate.unlink(missing_ok=True)
        except OSError:
            LOGGER.warning("Could not remove failed task output %s", candidate.name)


def process_song(
    app: Flask,
    sio: SocketIO,
    job_id: str,
    index: int,
    song: dict[str, str],
    reservation_bytes: int | None = None,
) -> None:
    """Process immutable job data without reading request/session state."""
    job = job_registry.get(job_id, touch=True)
    if job is None:
        return
    reserved = int(reservation_bytes or app.config["TASK_BYTE_RESERVATION"])
    output_base: Path | None = None
    retained = False

    def publish(status: str, message: str, progress_value: float | None = None, **extra: Any) -> None:
        payload: dict[str, Any] = {"job_id": job_id, "index": index, "status": status, "message": message}
        if progress_value is not None:
            payload["progress"] = round(progress_value, 1)
        payload.update(extra)
        with job.lock:
            job.statuses[index] = payload.copy()
            job.last_activity = job_registry.now()
        try:
            sio.emit("download_progress", payload, to=job_room(job_id))
        except Exception:
            LOGGER.exception("Could not emit progress for job %s track %s", job_id, index)

    semaphore: threading.BoundedSemaphore = app.extensions["download_semaphore"]
    try:
        with semaphore:
            publish("downloading", "Preparing audio", 0)
            filename = deterministic_filename(index, song)
            filepath = safe_artifact_path(job, filename, Path(app.config["DATA_ROOT"]))
            output_base = filepath.with_suffix("")

            def on_progress(percent: float | None, message: str) -> None:
                publish("downloading", message, percent)

            ffmpeg = resolve_ffmpeg(app.config.get("FFMPEG_PATH"))
            download_song_from_youtube(
                f"{song['Artist']} {song['Song']}",
                output_base,
                ffmpeg,
                on_progress,
                int(app.config["MAX_SOURCE_BYTES"]),
            )
            tag_mp3_file(filepath, song, int(app.config["ARTWORK_MAX_BYTES"]))
            actual_bytes = filepath.stat().st_size
            if actual_bytes > int(app.config["MAX_ARTIFACT_BYTES"]):
                raise ValueError("Downloaded file exceeds the configured size limit")
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
            artifact_url = f"/jobs/{job_id}/files/{quote(filename)}"
            publish("success", "Ready to download", 100, download_url=artifact_url)
    except Exception:
        LOGGER.exception("Job %s track %s failed", job_id, index)
        if not retained:
            _remove_task_outputs(output_base)
        with job.lock:
            job.failed.add(index)
        publish("failed", "Download failed. You can retry this track.")
    finally:
        job_registry.release_task(job, index, reserved)


def _csrf_token(app: Flask, job_id: str) -> str:
    secret = str(app.config["SECRET_KEY"]).encode()
    return hmac.new(secret, f"csrf:{job_id}".encode(), hashlib.sha256).hexdigest()


def _json_request() -> bool:
    return request.path.startswith("/api/") or request.is_json or "application/json" in request.headers.get("Accept", "")


def create_app(test_config: dict[str, Any] | None = None) -> Flask:
    load_dotenv()
    flask_app = Flask(__name__)
    default_root = Path(os.environ.get("DATA_ROOT", Path(tempfile.gettempdir()) / "spotifydownautomater"))
    flask_app.config.from_mapping(
        DATA_ROOT=str(default_root),
        MAX_CONTENT_LENGTH=2_000_000,
        CSV_MAX_BYTES=1_000_000,
        CSV_MAX_ROWS=2_000,
        CSV_MAX_FIELD_LENGTH=500,
        SELECTION_LIMIT=20,
        GLOBAL_CONCURRENCY=2,
        MAX_ACTIVE_TASKS_PER_JOB=8,
        MAX_SOURCE_BYTES=100_000_000,
        MAX_ARTIFACT_BYTES=100_000_000,
        TASK_BYTE_RESERVATION=None,
        MAX_JOB_BYTES=500_000_000,
        MAX_JOBS=100,
        MAX_TOTAL_JOB_BYTES=2_000_000_000,
        JOB_TTL_SECONDS=3_600,
        ZIP_MAX_BYTES=250_000_000,
        ARTWORK_MAX_BYTES=5_000_000,
        RATELIMIT_ENABLED=True,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
    )
    if test_config:
        flask_app.config.update(test_config)
    if flask_app.config["TASK_BYTE_RESERVATION"] is None:
        flask_app.config["TASK_BYTE_RESERVATION"] = flask_app.config["MAX_ARTIFACT_BYTES"]
    for limit_name in (
        "MAX_ACTIVE_TASKS_PER_JOB",
        "MAX_SOURCE_BYTES",
        "MAX_ARTIFACT_BYTES",
        "TASK_BYTE_RESERVATION",
        "MAX_JOB_BYTES",
        "MAX_JOBS",
        "MAX_TOTAL_JOB_BYTES",
    ):
        if int(flask_app.config[limit_name]) <= 0:
            raise ValueError(f"{limit_name} must be a positive integer")
    if float(flask_app.config["JOB_TTL_SECONDS"]) <= 0:
        raise ValueError("JOB_TTL_SECONDS must be positive")
    _configure_secret(flask_app, test_config)
    flask_app.config["SESSION_COOKIE_SECURE"] = bool(flask_app.config["PRODUCTION"])
    data_root = Path(flask_app.config["DATA_ROOT"]).expanduser().resolve()
    data_root.mkdir(parents=True, exist_ok=True)
    flask_app.config["DATA_ROOT"] = str(data_root)
    flask_app.extensions["download_semaphore"] = threading.BoundedSemaphore(
        int(flask_app.config["GLOBAL_CONCURRENCY"])
    )

    limiter = Limiter(
        key_func=get_remote_address,
        app=flask_app,
        default_limits=["120 per minute"],
        storage_uri="memory://",
        enabled=bool(flask_app.config["RATELIMIT_ENABLED"]),
    )
    # Flask-Limiter's route wrappers retain a weak reference; application
    # factories must keep the instance alive for the app's lifetime.
    flask_app.extensions["signal_forge_limiter"] = limiter
    sio = SocketIO(
        flask_app,
        async_mode="threading",
        cors_allowed_origins=None,
        manage_session=True,
        logger=False,
        engineio_logger=False,
    )
    flask_app.extensions["socketio_instance"] = sio

    @flask_app.before_request
    def reap_expired_jobs() -> None:
        job_registry.reap_expired(
            data_root,
            float(flask_app.config["JOB_TTL_SECONDS"]),
        )

    @flask_app.after_request
    def security_headers(response: Any) -> Any:
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "same-origin")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self' ws: wss:",
        )
        return response

    @flask_app.errorhandler(RequestEntityTooLarge)
    def too_large(_error: RequestEntityTooLarge) -> Any:
        message = "Upload exceeds the maximum request size"
        if _json_request():
            return jsonify(error=message), 413
        return render_current(message), 413

    @flask_app.errorhandler(429)
    def rate_limited(_error: HTTPException) -> Any:
        message = "Too many requests. Please wait and try again."
        if _json_request():
            return jsonify(error=message), 429
        return render_current(message), 429

    @flask_app.errorhandler(404)
    def not_found(_error: HTTPException) -> Any:
        if _json_request():
            return jsonify(error="Not found"), 404
        return render_current("The requested resource was not found"), 404

    @flask_app.errorhandler(JobCapacityError)
    def capacity_exhausted(error: JobCapacityError) -> Any:
        message = f"Service capacity is currently full. {error} Please try again later."
        if _json_request():
            return jsonify(error=message), 503
        return message, 503, {"Content-Type": "text/plain; charset=utf-8"}

    def create_job(songs: list[dict[str, str]] | None = None) -> Job:
        return job_registry.create(
            data_root,
            songs,
            int(flask_app.config["MAX_JOBS"]),
            int(flask_app.config["MAX_TOTAL_JOB_BYTES"]),
        )

    def ensure_current_job() -> Job:
        current = session.get("job_id")
        job = job_registry.get(current, touch=True)
        if job is None or job.lifecycle != "accepting":
            job = create_job()
            session.clear()
            session["job_id"] = job.job_id
        return job

    def owned_job(job_id: str | None = None) -> Job | None:
        current = session.get("job_id")
        requested = job_id or current
        if not current or requested != current:
            return None
        job = job_registry.get(current, touch=True)
        if job is None or job.lifecycle != "accepting":
            return None
        return job

    def csrf_valid(job: Job) -> bool:
        supplied = request.headers.get("X-CSRFToken") or request.form.get("csrf_token")
        return bool(supplied and hmac.compare_digest(supplied, _csrf_token(flask_app, job.job_id)))

    def mutation_job() -> tuple[Job | None, Any | None]:
        job = owned_job()
        if job is None:
            return None, (jsonify(error="Current job is unavailable; refresh the page"), 403)
        if not csrf_valid(job):
            return None, (jsonify(error="CSRF token is missing or invalid"), 400)
        return job, None

    def job_view(job: Job) -> dict[str, Any]:
        with job.lock:
            files = {
                str(index): url_for("download_file", job_id=job.job_id, filename=filename)
                for index, filename in job.files.items()
            }
            return {
                "job_id": job.job_id,
                "songs": list(job.songs),
                "statuses": dict(job.statuses),
                "files": files,
                "failed": sorted(job.failed),
                "active": job.active_count,
                "lifecycle": job.lifecycle,
                "reserved_bytes": job.reserved_bytes,
                "retained_bytes": job.retained_bytes,
            }

    def render_current(error_message: str | None = None, status: int = 200) -> Any:
        job = ensure_current_job()
        view = job_view(job)
        return render_template(
            "index.html",
            songs=view["songs"],
            job=view,
            csrf_token=_csrf_token(flask_app, job.job_id),
            selection_limit=flask_app.config["SELECTION_LIMIT"],
            csv_max_rows=flask_app.config["CSV_MAX_ROWS"],
            csv_max_bytes=flask_app.config["CSV_MAX_BYTES"],
            error_message=error_message,
        ), status

    @flask_app.route("/", methods=["GET"])
    @limiter.limit("60 per minute")
    def index() -> Any:
        return render_current()

    @flask_app.route("/upload", methods=["POST"])
    @limiter.limit("10 per minute")
    def upload_csv() -> Any:
        current, error_response = mutation_job()
        if error_response:
            return error_response
        assert current is not None
        try:
            songs = parse_csv_upload(request.files.get("csv_file"), flask_app.config)
        except ValueError as exc:
            return render_current(str(exc), 400)

        try:
            closed = job_registry.close_if_idle(current)
        except JobBusyError as exc:
            return render_current(str(exc), 409)
        except JobUnavailableError as exc:
            return render_current(str(exc), 409)
        try:
            confined = safe_job_directory(data_root, closed.job_id, closed.directory)
            if confined.exists():
                shutil.rmtree(confined)
        except Exception as exc:
            try:
                reconcile_job_storage(closed, data_root)
            except (OSError, ValueError):
                LOGGER.exception("Could not fully reconcile restored replacement job storage")
            job_registry.restore(closed)
            LOGGER.error("Could not replace job storage: %s", exc)
            return render_current("Could not replace this job; its existing state was restored", 500)
        try:
            replacement = job_registry.replace_closing(closed, data_root, songs)
        except Exception as exc:
            try:
                reconcile_job_storage(closed, data_root)
            except (OSError, ValueError):
                LOGGER.exception("Could not reconcile replacement allocation failure")
            job_registry.restore(closed)
            LOGGER.error("Could not allocate replacement job: %s", exc)
            return render_current("Could not create the replacement job; existing state was restored", 500)
        session.clear()
        session["job_id"] = replacement.job_id
        return render_current()

    def selected_from_request() -> Any:
        if request.is_json:
            payload = request.get_json(silent=True) or {}
            return payload.get("selected")
        return request.form.getlist("selected")

    def queue_indices(job: Job, indices: list[int]) -> list[int]:
        reservation = int(flask_app.config["TASK_BYTE_RESERVATION"])
        reserved = job_registry.reserve_indices(
            job,
            indices,
            int(flask_app.config["MAX_ACTIVE_TASKS_PER_JOB"]),
            reservation,
            int(flask_app.config["MAX_JOB_BYTES"]),
            int(flask_app.config["MAX_TOTAL_JOB_BYTES"]),
        )
        started: list[int] = []
        for index in reserved:
            copied_song = dict(job.songs[index])
            try:
                sio.start_background_task(
                    process_song,
                    flask_app,
                    sio,
                    job.job_id,
                    index,
                    copied_song,
                    reservation,
                )
            except Exception:
                LOGGER.exception("Could not start job %s track %s", job.job_id, index)
                job_registry.release_task(job, index, reservation, "Could not start background task")
            else:
                started.append(index)
        if reserved and not started:
            raise JobAdmissionError("Could not start background tasks")
        return started

    @flask_app.route("/download", methods=["POST"])
    @limiter.limit("20 per minute")
    def download_songs() -> Any:
        job, error_response = mutation_job()
        if error_response:
            return error_response
        assert job is not None
        try:
            indices = validate_selection(
                selected_from_request(), len(job.songs), int(flask_app.config["SELECTION_LIMIT"])
            )
        except ValueError as exc:
            return jsonify(error=str(exc)), 400
        try:
            started = queue_indices(job, indices)
        except (JobAdmissionError, JobUnavailableError) as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(job_id=job.job_id, started=started), 202

    @flask_app.route("/retry-failed", methods=["POST"])
    @limiter.limit("20 per minute")
    def retry_failed_downloads() -> Any:
        job, error_response = mutation_job()
        if error_response:
            return error_response
        assert job is not None
        with job.lock:
            indices = sorted(job.failed)[: int(flask_app.config["SELECTION_LIMIT"])]
        if not indices:
            return jsonify(error="There are no failed downloads to retry"), 409
        try:
            started = queue_indices(job, indices)
        except (JobAdmissionError, JobUnavailableError) as exc:
            return jsonify(error=str(exc)), 409
        return jsonify(job_id=job.job_id, started=started), 202

    @flask_app.route("/api/jobs/<job_id>", methods=["GET"])
    @limiter.limit("60 per minute")
    def job_status(job_id: str) -> Any:
        job = owned_job(job_id)
        if job is None:
            return jsonify(error="Job not found"), 404
        return jsonify(job_view(job))

    @flask_app.route("/jobs/<job_id>/files/<path:filename>", methods=["GET"])
    @limiter.limit("60 per minute")
    def download_file(job_id: str, filename: str) -> Any:
        job = owned_job(job_id)
        if job is None:
            return jsonify(error="File not found"), 404
        with job.lock:
            if filename not in job.files.values():
                return jsonify(error="File not found"), 404
        try:
            filepath = safe_artifact_path(job, filename, data_root)
        except ValueError:
            return jsonify(error="File not found"), 404
        if not filepath.is_file():
            return jsonify(error="File not found"), 404
        return send_file(filepath, as_attachment=True, download_name=filename)

    @flask_app.route("/download_zip", methods=["POST"])
    @limiter.limit("10 per minute")
    def download_zip() -> Any:
        job, error_response = mutation_job()
        if error_response:
            return error_response
        assert job is not None
        with job.lock:
            if job.active_count:
                return jsonify(error="Wait for active downloads before creating a ZIP"), 409
            filenames = list(job.files.values())
        if not filenames:
            return jsonify(error="No completed downloads are available"), 409

        paths: list[Path] = []
        total = 0
        for filename in filenames:
            try:
                path = safe_artifact_path(job, filename, data_root)
            except ValueError:
                return jsonify(error="A job artifact is invalid"), 409
            if not path.is_file():
                continue
            total += path.stat().st_size
            if total > int(flask_app.config["ZIP_MAX_BYTES"]):
                return jsonify(error="Completed files exceed the ZIP size limit"), 413
            paths.append(path)
        if not paths:
            return jsonify(error="No completed downloads are available"), 409

        temp = tempfile.NamedTemporaryFile(prefix=f"{job.job_id}-", suffix=".zip", delete=False)
        temp_path = Path(temp.name)
        temp.close()
        try:
            with zipfile.ZipFile(temp_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                for path in paths:
                    archive.write(path, arcname=path.name)
        except Exception:
            temp_path.unlink(missing_ok=True)
            raise

        @after_this_request
        def remove_zip(response: Any) -> Any:
            response.call_on_close(lambda: temp_path.unlink(missing_ok=True))
            return response

        return send_file(
            temp_path,
            mimetype="application/zip",
            as_attachment=True,
            download_name=f"audio-job-{job.job_id[:8]}.zip",
        )

    @flask_app.route("/cleanup", methods=["POST"])
    @limiter.limit("10 per minute")
    def cleanup_downloads() -> Any:
        job, error_response = mutation_job()
        if error_response:
            return error_response
        assert job is not None
        try:
            confined = safe_job_directory(data_root, job.job_id, job.directory)
        except ValueError:
            return jsonify(error="Job storage failed path validation"), 409
        try:
            closed = job_registry.close_if_idle(job)
        except (JobBusyError, JobUnavailableError) as exc:
            return jsonify(error=str(exc)), 409
        try:
            if confined.exists():
                shutil.rmtree(confined)
        except Exception as exc:
            try:
                reconcile_job_storage(closed, data_root)
            except (OSError, ValueError):
                LOGGER.exception("Could not fully reconcile restored cleanup job storage")
            job_registry.restore(closed)
            LOGGER.error("Could not delete job storage: %s", exc)
            return jsonify(error="Could not clear job storage; the job was restored"), 500
        try:
            replacement = job_registry.replace_closing(closed, data_root)
        except Exception as exc:
            try:
                reconcile_job_storage(closed, data_root)
            except (OSError, ValueError):
                LOGGER.exception("Could not reconcile cleanup replacement allocation failure")
            job_registry.restore(closed)
            LOGGER.error("Could not allocate cleanup replacement job: %s", exc)
            return jsonify(error="Could not create a replacement job; the prior job was restored"), 500
        session.clear()
        session["job_id"] = replacement.job_id
        return jsonify(
            cleared=True,
            job_id=replacement.job_id,
            csrf_token=_csrf_token(flask_app, replacement.job_id),
        )

    @sio.on("join_job")
    def join_job(payload: Any) -> None:
        requested = payload.get("job_id") if isinstance(payload, dict) else None
        job = owned_job(requested)
        if job is None:
            emit("join_error", {"error": "Job not found"})
            return
        join_room(job_room(job.job_id))
        emit("joined_job", {"job_id": job.job_id})

    return flask_app


logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
app = create_app()
socketio: SocketIO = app.extensions["socketio_instance"]


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "5000")), debug=False)
