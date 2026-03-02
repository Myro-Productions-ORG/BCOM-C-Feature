#!/bin/bash
set -e
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
swiftc "$SCRIPT_DIR/main.swift" -o "$SCRIPT_DIR/media-key-tap" -framework AppKit -framework Foundation -framework MediaPlayer
echo "Built: $SCRIPT_DIR/media-key-tap"
