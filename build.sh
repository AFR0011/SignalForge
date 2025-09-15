#!/usr/bin/env bash

echo "Setting up ffmpeg..."

# Make bin dir if not exists
mkdir -p bin

# Download static build of ffmpeg (compatible with most Linux systems)
curl -L https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz -o ffmpeg.tar.xz

# Extract
tar -xf ffmpeg.tar.xz

# Move ffmpeg binary to bin/
mv ffmpeg-*-static/ffmpeg bin/ffmpeg

# Make executable
chmod +x bin/ffmpeg

# Cleanup
rm -rf ffmpeg.tar.xz ffmpeg-*-static

echo "ffmpeg is set up at ./bin/ffmpeg"

# Install Python dependencies
pip install -r requirements.txt
