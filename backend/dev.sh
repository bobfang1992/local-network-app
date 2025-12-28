#!/bin/bash

# Development mode with auto-restart on file changes
# Usage: sudo ./dev.sh

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="${SCRIPT_DIR}/.venv/bin/python"
WATCH_SCRIPT="${SCRIPT_DIR}/dev-watch.py"

echo "Starting development mode with auto-restart..."
echo ""

# Run the watch script with sudo (if passwordless sudo is configured)
sudo "${PYTHON_PATH}" "${WATCH_SCRIPT}"
