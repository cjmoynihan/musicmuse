#!/usr/bin/env bash
./generate_song_suggestions.py
python3 -m http.server 8000
