#!/bin/bash
set -euo pipefail

TARGET_PATH="${1:-$HOME/.local-network/oui.csv}"
TARGET_DIR="$(dirname "$TARGET_PATH")"

mkdir -p "$TARGET_DIR"

echo "Downloading IEEE OUI database..."
curl -fsSL "https://standards-oui.ieee.org/oui/oui.csv" -o "$TARGET_PATH"
echo "Saved OUI database to: $TARGET_PATH"
