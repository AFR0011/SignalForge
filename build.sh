#!/usr/bin/env bash

# Create bin directory
mkdir -p bin

# Download ffmpeg 64-bit static build
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz | tar xJ --strip-components=1 -C bin
chmod +x bin/ffmpeg

# Download yt-dlp binary
curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o bin/yt-dlp
chmod +x bin/yt-dlp

# Add bin to PATH (so ffmpeg is usable)
export PATH="$PWD/bin:$PATH"

# Install Python dependencies
pip install -r requirements.txt
