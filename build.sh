#!/usr/bin/env bash

# Download ffmpeg static build
mkdir -p bin
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-i686-static.tar.xz | tar xJ --strip-components=1 -C bin
chmod +x bin/ffmpeg

# Download yt-dlp binary
curl -L https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp -o bin/yt-dlp
chmod +x bin/yt-dlp
