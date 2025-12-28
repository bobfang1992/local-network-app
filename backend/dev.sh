#!/bin/bash

# Development mode with auto-restart on file changes
# Usage: sudo ./dev.sh [--debug]

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="${SCRIPT_DIR}/.venv/bin/python"
WATCH_SCRIPT="${SCRIPT_DIR}/dev-watch.py"

echo "Starting development mode with auto-restart..."
echo ""

# Run the watch script with sudo, passing through any arguments
sudo "${PYTHON_PATH}" "${WATCH_SCRIPT}" "$@"
