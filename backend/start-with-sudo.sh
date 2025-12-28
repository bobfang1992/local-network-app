#!/bin/bash

echo "Starting FastAPI backend with sudo (for full network scanning)..."
echo ""

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="${SCRIPT_DIR}/.venv/bin/python"
MAIN_PATH="${SCRIPT_DIR}/main.py"

# Use absolute paths to match sudoers whitelist (no password prompt)
sudo "${PYTHON_PATH}" "${MAIN_PATH}"
