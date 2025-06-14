import os
import re
import pandas as pd
from flask import Flask, render_template, request, redirect, send_from_directory
from yt_dlp import YoutubeDL
from mutagen.easyid3 import EasyID3
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, APIC, error
import requests
from flask import jsonify, request as flask_request

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["DOWNLOAD_FOLDER"] = "downloads"

os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
os.makedirs(app.config["DOWNLOAD_FOLDER"], exist_ok=True)

songs = []
failed_downloads = set()

# ---- Utilities ----

def sanitize_filename(name):
    return re.sub(r'[\\/*?:"<>|]', "", name)

def format_title(raw_title):
    title = raw_title.strip()
    # Remove (feat...) or (ft...)
    title = re.sub(r"\s*\((?:feat|ft)\.?[^)]*\)", "", title, flags=re.I)

    # Normalize Slowed/Sped Up etc.
    if re.search(r"\bslowed\b", title, flags=re.I):
        title = re.sub(r"\s*(slowed|slowed remix)[^)]*$", "", title, flags=re.I)
        title = title.strip() + " (Slowed)"
    elif re.search(r"\b(sped up|speed up|speedup|speed-up)\b", title, flags=re.I):
        title = re.sub(r"\s*(sped up|speed up|speedup|speed-up)[^)]*$", "", title, flags=re.I)
        title = title.strip() + " (Sped Up)"
    # Remove _ and -
    title = re.sub(r"\s?[_-]+\s?", " ", title, flags=re.I)
    # Title Case (smart)
    title = title.lower().title()
    title = re.sub(r"('S)\b", "'s", title)
    title = re.sub(r"('T)\b", "'t", title)
    return title

def unique_path(base_path):
    path = base_path
    while os.path.exists(f"{path}.mp3"):
        path += " "
    return f"{path}.mp3"

def fetch_cover_art(song_title, artist_name):
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
        print(f"[Cover Art] Failed to fetch: {e}")
    return None

def tag_mp3(filepath, title, artist, album=None, genres=None):
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
        # genres can be comma-separated or a list
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
            print(f"[Cover Art] Embedded for {filepath}")
        except error as e:
            print(f"[Cover Art] Failed to embed: {e}")

# ---- Routes ----

@app.route("/", methods=["GET", "POST"])
def index():
    global songs
    if request.method == "POST":
        file = request.files["csv_file"]
        if file and file.filename.endswith(".csv"):
            path = os.path.join(app.config["UPLOAD_FOLDER"], file.filename)
            file.save(path)
            df = pd.read_csv(path)
            songs = df.to_dict(orient="records")
            return render_template("index.html", songs=songs)
    return render_template("index.html", songs=[])

@app.route("/download", methods=["POST"])
def download_song():
    selected_indices = request.form.getlist("selected")
    for idx in selected_indices:
        idx = int(idx)
        song = songs[idx]
        raw_title = song.get("Song") or song.get("Title")
        artist = song.get("Artist", "")
        album = song.get("Album", "")
        genres = song.get("Genres", "")

        formatted_title = format_title(raw_title)
        query = f"{artist} {raw_title}"

        sanitized = sanitize_filename(formatted_title)
        base_path = os.path.join(app.config["DOWNLOAD_FOLDER"], sanitized)
        output_file = unique_path(base_path)
        outtmpl = output_file.replace(".mp3", ".%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "ffmpeg_location": "C:\\ffmpeg\\bin",
            "postprocessors": [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }],
            "quiet": True,
            "noplaylist": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            try:
                ydl.download([f"ytsearch1:{query}"])
                tag_mp3(output_file, formatted_title, artist, album, genres)
            except Exception as e:
                print(f"[Download Error] {query}: {e}")

    return redirect("/downloads")


@app.route("/downloads")
def list_downloads():
    files = os.listdir(app.config["DOWNLOAD_FOLDER"])
    return render_template("downloads.html", files=files)

@app.route("/downloads/<filename>")
def download_file(filename):
    return send_from_directory(app.config["DOWNLOAD_FOLDER"], filename, as_attachment=True)

@app.route("/download-ajax", methods=["POST"])
def download_ajax():
    try:
        data = flask_request.get_json()
        idx = int(data.get("index"))
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
        outtmpl = output_file.replace(".mp3", ".%(ext)s")

        ydl_opts = {
            "format": "bestaudio/best",
            "outtmpl": outtmpl,
            "ffmpeg_location": "C:\\ffmpeg\\bin",
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "192",
                }
            ],
            "quiet": True,
            "noplaylist": True,
        }

        with YoutubeDL(ydl_opts) as ydl:
            ydl.download([f"ytsearch1:{query}"])
            tag_mp3(output_file, formatted_title, artist, album, genres)

        return jsonify({"success": True})

    except Exception as e:
        print(f"Download error: {e}")
        failed_downloads.add(idx)
        return jsonify({"success": False, "error": str(e)})
@app.route("/retry-failed", methods=["POST"])
def retry_failed():
    results = []
    to_retry = list(failed_downloads)

    for idx in to_retry:
        try:
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
            outtmpl = output_file.replace(".mp3", ".%(ext)s")

            ydl_opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "ffmpeg_location": "C:\\ffmpeg\\bin",
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "192",
                    }
                ],
                "quiet": True,
                "noplaylist": True,
            }

            with YoutubeDL(ydl_opts) as ydl:
                ydl.download([f"ytsearch1:{query}"])
                tag_mp3(output_file, formatted_title, artist, album, genres)

            failed_downloads.discard(idx)
            results.append({"index": idx, "success": True})
        except Exception as e:
            results.append({"index": idx, "success": False, "error": str(e)})

    return jsonify(results)



if __name__ == "__main__":
    app.run(debug=True)
