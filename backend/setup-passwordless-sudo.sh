#!/bin/bash

# Setup passwordless sudo for the backend Python process
# This allows running the network scanner without entering password each time

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYTHON_PATH="${SCRIPT_DIR}/.venv/bin/python"
MAIN_PATH="${SCRIPT_DIR}/main.py"
USER=$(whoami)

echo "=================================================="
echo "Passwordless Sudo Setup for Network Scanner"
echo "=================================================="
echo ""
echo "This will configure sudoers to allow:"
echo "  ${PYTHON_PATH} ${MAIN_PATH}"
echo ""
echo "to run without password prompt."
echo ""
echo "⚠️  You'll need to enter your password ONCE to set this up."
echo ""
read -p "Continue? (y/n) " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Aborted."
    exit 1
fi

# Create sudoers entry
SUDOERS_ENTRY="${USER} ALL=(root) NOPASSWD: ${PYTHON_PATH} ${MAIN_PATH}"
SUDOERS_FILE="/etc/sudoers.d/local-network-scanner"

echo ""
echo "Creating sudoers file: ${SUDOERS_FILE}"
echo "Entry: ${SUDOERS_ENTRY}"
echo ""

# Create temporary file with the entry
TEMP_FILE=$(mktemp)
echo "# Allow ${USER} to run network scanner without password" > "$TEMP_FILE"
echo "# Created by setup-passwordless-sudo.sh on $(date)" >> "$TEMP_FILE"
echo "${SUDOERS_ENTRY}" >> "$TEMP_FILE"

# Validate the sudoers syntax
if sudo visudo -c -f "$TEMP_FILE" > /dev/null 2>&1; then
    echo "✓ Sudoers syntax is valid"

    # Install the sudoers file
    sudo cp "$TEMP_FILE" "$SUDOERS_FILE"
    sudo chmod 440 "$SUDOERS_FILE"

    echo ""
    echo "=================================================="
    echo "✓ Setup Complete!"
    echo "=================================================="
    echo ""
    echo "You can now run the backend without entering password:"
    echo "  ./start-with-sudo.sh"
    echo ""
    echo "To remove this configuration later:"
    echo "  sudo rm ${SUDOERS_FILE}"
    echo ""
else
    echo "✗ Error: Invalid sudoers syntax"
    rm "$TEMP_FILE"
    exit 1
fi

# Clean up
rm "$TEMP_FILE"
