import os
import re
import logging
import pandas as pd
from flask import Flask, render_template, request, send_from_directory, jsonify, send_file
from flask_wtf.csrf import CSRFProtect
from wtforms import FileField
from flask_wtf import FlaskForm
from flask_socketio import SocketIO, emit
from yt_dlp import YoutubeDL, DownloadError
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error
import requests
from math import isnan
from mutagen.id3 import ID3NoHeaderError
import zipfile
from io import BytesIO
from dotenv import load_dotenv

app = Flask(__name__)

# Load environment variables and configure secret key for CSRF/session
load_dotenv()
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-change-me")

app.config["UPLOAD_FOLDER"] = "/tmp/uploads"
app.config["DOWNLOAD_FOLDER"] = "/tmp/downloads"

# Initialize CSRF protection
csrf = CSRFProtect(app)

# Initialize SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["DOWNLOAD_FOLDER"], exist_ok=True)

songs = []
failed_downloads = set()
successful_downloads = set()  # Track successful downloads

# Form for CSV upload with CSRF
class UploadForm(FlaskForm):
    csv_file = FileField("CSV File")

# ---- Utility Functions ----

def sanitize_metadata_field(value):
    """Sanitize metadata fields by handling None or NaN values and stripping whitespace."""
    if value is None:
        return ""
    if isinstance(value, float) and isnan(value):
        return ""
    return str(value).strip()

def sanitize_filename(name):
    """Remove invalid characters from filenames."""
    return re.sub(r'[\\/*?:"<>|]', "", name)

def format_title(raw_title):
    """Clean and format song titles by removing unwanted text and normalizing variations."""
    title = raw_title.strip()
    title = re.sub(r"\s*\((?:feat|ft)\.?[^)]*\)", "", title, flags=re.I)
    if re.search(r"\bslowed\b", title, flags=re.I):
        title = re.sub(r"\s*(slowed|slowed remix)[^)]*$", "", title, flags=re.I)
        title = title.strip() + " (Slowed)"
    elif re.search(r"\b(sped up|speed up|speedup|speed-up)\b", title, flags=re.I):
        title = re.sub(r"\s*(sped up|speed up|speedup|speed-up)[^)]*$", "", title, flags=re.I)
        title = title.strip() + " (Sped Up)"
    title = re.sub(r"\s?[_-]+\s?", " ", title, flags=re.I)
    title = title.lower().title()
    title = re.sub(r"('S)\b", "'s", title)
    title = re.sub(r"('T)\b", "'t", title)
    return title

def unique_path(base_path):
    """Generate a unique file path by appending a number if the file already exists."""
    path = os.path.normpath(base_path)  # Normalize path separators
    counter = 1
    while os.path.exists(f"{path}.mp3"):
        path = os.path.normpath(f"{base_path} ({counter})")
        counter += 1
    return path  # Return path without .mp3 extension

def fetch_cover_art(song_title, artist_name):
    """Fetch cover art from iTunes based on song title and artist."""
    query = f"{song_title} {artist_name}".strip().replace(" ", "+")
    url = f"https://itunes.apple.com/search?term={query}&entity=song&limit=1"
    try:
        resp = requests.get(url, timeout=5)
        results = resp.json().get("results")
        if results:
            artwork_url = results[0].get("artworkUrl100")
            if artwork_url:
                artwork_url = artwork_url.replace("100x100", "600x600")
                image_resp = requests.get(artwork_url, timeout=5)
                return image_resp.content
    except Exception as e:
        logging.error(f"[Cover Art] Failed to fetch: {e}")
    return None

def tag_mp3_file(filepath, title, artist, album, genres):
    """Tag an MP3 file with metadata and cover art."""
    filepath = os.path.normpath(filepath)  # Normalize path
    if not os.path.exists(filepath):
        logging.error(f"Cannot tag file {filepath}: File does not exist")
        raise FileNotFoundError(f"File {filepath} does not exist for tagging")
    
    title = sanitize_metadata_field(title)
    artist = sanitize_metadata_field(artist)
    album = sanitize_metadata_field(album)
    genres = sanitize_metadata_field(genres)

    try:
        audio = EasyID3(filepath)
    except Exception:
        audio = MP3(filepath, ID3=EasyID3)
        audio.add_tags()

    audio["title"] = title
    audio["artist"] = artist
    if album:
        audio["album"] = album
    if genres:
        if isinstance(genres, str):
            genres = [g.strip() for g in genres.split(",")]
        audio["genre"] = genres
    audio.save()

    cover_data = fetch_cover_art(title, artist.split(",")[0])
    if cover_data:
        try:
            audio = MP3(filepath, ID3=ID3)
            audio.tags.add(
                APIC(
                    encoding=3,
                    mime="image/jpeg",
                    type=3,
                    desc="Cover",
                    data=cover_data,
                )
            )
            audio.save()
            logging.info(f"[Cover Art] Embedded for {filepath}")
        except error as e:
            logging.error(f"[Cover Art] Failed to embed: {e}")

def check_existing_file(filepath, title, artist, album):
    """Check if a file exists with matching metadata."""
    filepath = os.path.normpath(filepath)  # Normalize path
    if not os.path.exists(filepath):
        return False
    try:
        audio = EasyID3(filepath)
        current_title = audio.get("title", [""])[0]
        current_artist = audio.get("artist", [""])[0]
        current_album = audio.get("album", [""])[0]
        has_cover = False
        try:
            mp3 = MP3(filepath, ID3=ID3)
            has_cover = any(isinstance(frame, APIC) for frame in mp3.tags.values())
        except ID3NoHeaderError:
            has_cover = False
        return (
            current_title == title
            and current_artist == artist
            and current_album == album
            and has_cover
        )
    except Exception as e:
        logging.error(f"[Metadata Check] Failed: {e}")
        return False

def download_song_from_youtube(query, output_file, idx):
    """Download a song from YouTube using yt-dlp with progress updates."""
    output_file = os.path.normpath(output_file)  # Normalize path
    final_path = f"{output_file}.mp3"
    logging.info(f"Downloading to: {final_path}")

    def progress_hook(d):
        """Emit progress updates via SocketIO."""
        if d["status"] == "downloading":
            percent = d.get("downloaded_bytes", 0) / d.get("total_bytes", 1) * 100
            socketio.emit("download_progress", {
                "index": idx,
                "status": "downloading",
                "progress": round(percent, 1),
                "message": f"Downloading {percent:.1f}%"
            })
        elif d["status"] == "finished":
            socketio.emit("download_progress", {
                "index": idx,
                "status": "finished",
                "message": "Processing metadata"
            })

    class MyLogger:
        def debug(self, msg): pass
        def warning(self, msg): logging.warning(msg)
        def error(self, msg): logging.error(msg)

    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": f"{output_file}.%(ext)s",  # Use normalized output_file
        "ffmpeg_location": "./bin/ffmpeg",
        "logger": MyLogger(),
        "progress_hooks": [progress_hook],
        "postprocessors": [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }
        ],
        "quiet": False,
        "noplaylist": True,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
        # Verify the file was created
        if not os.path.exists(final_path):
            raise FileNotFoundError(f"Download failed to create file: {final_path}")
        logging.info(f"Successfully downloaded: {final_path}")
    except DownloadError as e:
        logging.error(f"yt-dlp download failed for {query}: {str(e)}")
        raise
    except Exception as e:
        logging.error(f"Unexpected error during download for {query}: {str(e)}")
        raise

# ---- Routes ----

@app.route("/", methods=["GET", "POST"])
def index():
    """Handle CSV upload and display song list."""
    global songs
    form = UploadForm()
    if form.validate_on_submit():
        file = form.csv_file.data
        if file and file.filename.endswith(".csv"):
            path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(path)
            try:
                df = pd.read_csv(path)
                required_columns = ["Song", "Artist"]
                if not all(col in df.columns for col in required_columns):
                    return "CSV missing required columns", 400
                songs = df.to_dict(orient="records")
                logging.info(f"Loaded {len(songs)} songs from CSV")
                return render_template("index.html", songs=songs, form=form)
            except Exception as e:
                logging.error(f"Failed to process CSV: {e}")
                return "Invalid CSV file", 400
    return render_template("index.html", songs=[], form=form)

@app.route("/download", methods=["POST"])
def download_songs():
    """Download selected songs and return status."""
    global failed_downloads, successful_downloads
    selected_indices = request.form.getlist("selected")
    results = []
    for idx in selected_indices:
        idx = int(idx)
        if idx >= len(songs):
            logging.error(f"Invalid song index: {idx}")
            results.append({"index": idx, "status": "failed", "error": "Invalid song index"})
            failed_downloads.add(idx)
            socketio.emit("download_progress", {
                "index": idx,
                "status": "failed",
                "message": "Invalid song index"
            })
            continue

        song = songs[idx]
        raw_title = song.get("Song") or song.get("Title")
        artist = song["Artist"]
        album = song.get("Album", "")
        genres = song.get("Genres", "")

        formatted_title = format_title(raw_title)
        query = f"{artist} {raw_title}"
        sanitized = sanitize_filename(formatted_title)
        base_path = os.path.join(app.config["DOWNLOAD_FOLDER"], sanitized)
        output_file = unique_path(base_path)
        filepath = f"{output_file}.mp3"
        logging.info(f"Attempting to download song {idx} to {filepath}")

        socketio.emit("download_progress", {
            "index": idx,
            "status": "downloading",
            "progress": 0,
            "message": "Starting download"
        })

        try:
            if not check_existing_file(filepath, formatted_title, artist, album):
                download_song_from_youtube(query, output_file, idx)
                tag_mp3_file(filepath, formatted_title, artist, album, genres)
            else:
                logging.info(f"Skipping download for song {idx}: File exists with matching metadata")
                socketio.emit("download_progress", {
                    "index": idx,
                    "status": "success",
                    "message": "Downloaded (already exists)"
                })
            results.append({"index": idx, "status": "success"})
            failed_downloads.discard(idx)
            successful_downloads.add((idx, filepath))  # Track successful download
            socketio.emit("download_progress", {
                "index": idx,
                "status": "success",
                "message": "Downloaded"
            })
        except FileNotFoundError as e:
            logging.error(f"Download failed for song {idx}: {str(e)}")
            results.append({"index": idx, "status": "failed", "error": str(e)})
            failed_downloads.add(idx)
            socketio.emit("download_progress", {
                "index": idx,
                "status": "failed",
                "message": str(e)
            })
        except Exception as e:
            logging.error(f"Download failed for song {idx}: {str(e)}")
            results.append({"index": idx, "status": "failed", "error": str(e)})
            failed_downloads.add(idx)
            socketio.emit("download_progress", {
                "index": idx,
                "status": "failed",
                "message": str(e)
            })
    return jsonify({"results": results})

@app.route("/retry-failed", methods=["POST"])
def retry_failed_downloads():
    """Retry downloading songs that previously failed."""
    global failed_downloads, successful_downloads
    results = []
    for idx in list(failed_downloads):
        if idx >= len(songs):
            logging.error(f"Invalid song index for retry: {idx}")
            results.append({"index": idx, "status": "failed", "error": "Invalid song index"})
            socketio.emit("download_progress", {
                "index": idx,
                "status": "failed",
                "message": "Invalid song index"
            })
            continue

        song = songs[idx]
        raw_title = song.get("Song") or song.get("Title")
        artist = song["Artist"]
        album = song.get("Album", "")
        genres = song.get("Genres", "")

        formatted_title = format_title(raw_title)
        query = f"{artist} {raw_title}"
        sanitized = sanitize_filename(formatted_title)
        base_path = os.path.join(app.config["DOWNLOAD_FOLDER"], sanitized)
        output_file = unique_path(base_path)
        filepath = f"{output_file}.mp3"
        logging.info(f"Retrying download for song {idx} to {filepath}")

        socketio.emit("download_progress", {
            "index": idx,
            "status": "downloading",
            "progress": 0,
            "message": "Starting retry"
        })

        try:
            if not check_existing_file(filepath, formatted_title, artist, album):
                download_song_from_youtube(query, output_file, idx)
                tag_mp3_file(filepath, formatted_title, artist, album, genres)
            else:
                logging.info(f"Skipping retry for song {idx}: File exists with matching metadata")
                socketio.emit("download_progress", {
                    "index": idx,
                    "status": "success",
                    "message": "Downloaded (already exists)"
                })
            failed_downloads.discard(idx)
            successful_downloads.add((idx, filepath))  # Track successful download
            results.append({"index": idx, "status": "success"})
            socketio.emit("download_progress", {
                "index": idx,
                "status": "success",
                "message": "Downloaded"
            })
        except FileNotFoundError as e:
            logging.error(f"Retry failed for song {idx}: {str(e)}")
            results.append({"index": idx, "status": "failed", "error": str(e)})
            socketio.emit("download_progress", {
                "index": idx,
                "status": "failed",
                "message": str(e)
            })
        except Exception as e:
            logging.error(f"Retry failed for song {idx}: {str(e)}")
            results.append({"index": idx, "status": "failed", "error": str(e)})
            socketio.emit("download_progress", {
                "index": idx,
                "status": "failed",
                "message": str(e)
            })
    return jsonify(results)

@app.route("/downloads/<filename>")
def download_file(filename):
    """Serve a downloaded MP3 file."""
    return send_from_directory(app.config["DOWNLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/downloads/list")
def partial_downloads_list():
    """Render a partial list of downloaded files."""
    files = os.listdir(app.config["DOWNLOAD_FOLDER"])
    return render_template("partials/download_list.html", files=files)

@app.route("/download_zip", methods=["POST"])
def download_zip():
    """Create and serve a ZIP file of all downloaded MP3s."""
    global successful_downloads
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        for idx, filepath in successful_downloads:
            if os.path.exists(filepath):
                arcname = os.path.basename(filepath)
                zf.write(filepath, arcname=arcname)
            else:
                logging.warning(f"File {filepath} not found for ZIP")
    memory_file.seek(0)
    return send_file(
        memory_file,
        mimetype="application/zip",
        as_attachment=True,
        download_name="downloaded_songs.zip"
    )

if __name__ == "__main__":
    socketio.run(app, debug=True)