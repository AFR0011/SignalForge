import os
import pandas as pd
from flask import Flask, render_template, request, redirect, send_from_directory
from yt_dlp import YoutubeDL
from mutagen.easyid3 import EasyID3

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = 'uploads'
app.config['DOWNLOAD_FOLDER'] = 'downloads'

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['DOWNLOAD_FOLDER'], exist_ok=True)

songs = []

# Tag downloaded MP3
def tag_mp3(filepath, song, artist):
    from mutagen.mp3 import MP3
    try:
        audio = EasyID3(filepath)
    except Exception:
        audio = MP3(filepath, ID3=EasyID3)
        audio.add_tags()
    audio['song'] = song
    audio['artist'] = artist
    audio.save()

# Route: Upload CSV
@app.route('/', methods=['GET', 'POST'])
def index():
    global songs
    if request.method == 'POST':
        file = request.files['csv_file']
        if file and file.filename.endswith('.csv'):
            path = os.path.join(app.config['UPLOAD_FOLDER'], file.filename)
            file.save(path)
            df = pd.read_csv(path)
            songs = df.to_dict(orient='records')
            return render_template('index.html', songs=songs)
    return render_template('index.html', songs=[])

# Route: Download selected song
@app.route('/download', methods=['POST'])
def download_song():
    selected_indices = request.form.getlist('selected')
    downloaded_files = []

    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': os.path.join(app.config['DOWNLOAD_FOLDER'], '%(artist)s - %(title)s.%(ext)s'),
        'ffmpeg_location': 'C:\\ffmpeg\\bin',
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'quiet': True,
        'noplaylist': True,
    }

    for idx in selected_indices:
        idx = int(idx)
        song = songs[idx]
        query = f"{song['Artist']} {song['Song']}"

        with YoutubeDL(ydl_opts) as ydl:
            try:
                info = ydl.extract_info(f"ytsearch1:{query}", download=True)
                downloaded_title = info['entries'][0]['title']
                file_path = os.path.join(app.config['DOWNLOAD_FOLDER'], f"{downloaded_title}.mp3")

                if os.path.exists(file_path):
                    tag_mp3(file_path, song['Song'], song['Artist'])
                    downloaded_files.append(file_path)
            except Exception as e:
                print(f"Error downloading {query}: {e}")

    return redirect('/downloads')

# Route: Show downloaded files
@app.route('/downloads')
def list_downloads():
    files = os.listdir(app.config['DOWNLOAD_FOLDER'])
    return render_template('downloads.html', files=files)

# Route: Serve a file
@app.route('/downloads/<filename>')
def download_file(filename):
    return send_from_directory(app.config['DOWNLOAD_FOLDER'], filename, as_attachment=True)

if __name__ == '__main__':
    app.run(debug=True)
