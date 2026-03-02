#!/bin/bash
# bob.sh — launch the Bob control dashboard
# Usage: ./bob.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$SCRIPT_DIR/src/orchestrator/venv/bin/python" "$SCRIPT_DIR/src/process-manager/app.py"
