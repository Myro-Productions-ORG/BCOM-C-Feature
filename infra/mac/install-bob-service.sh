#!/usr/bin/env bash
# Install Bob Control as a persistent launchd service on this Mac.
# Run once; re-run to update after changing the plist.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$REPO_ROOT/infra/mac/com.myroproductions.bob-control.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.myroproductions.bob-control.plist"
LABEL="com.myroproductions.bob-control"
LOG_DIR="$HOME/logs"

echo "==> Installing Bob Control service"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Stop existing service if loaded
if launchctl list | grep -q "$LABEL" 2>/dev/null; then
    echo "  Unloading existing service..."
    launchctl unload "$PLIST_DST" 2>/dev/null || true
fi

# Copy plist to LaunchAgents
cp "$PLIST_SRC" "$PLIST_DST"
echo "  Copied plist to $PLIST_DST"

# Load the service
launchctl load "$PLIST_DST"
echo "  Loaded service"

# Give it a moment to start
sleep 2

# Verify
if launchctl list | grep -q "$LABEL"; then
    echo ""
    echo "Bob Control is running at http://localhost:7766"
    echo ""
    echo "Useful commands:"
    echo "  logs:    tail -f $LOG_DIR/bob-control.log"
    echo "  errors:  tail -f $LOG_DIR/bob-control.error.log"
    echo "  stop:    launchctl unload $PLIST_DST"
    echo "  restart: launchctl unload $PLIST_DST && launchctl load $PLIST_DST"
else
    echo ""
    echo "ERROR: Service did not start. Check logs:"
    echo "  tail -f $LOG_DIR/bob-control.error.log"
    exit 1
fi
