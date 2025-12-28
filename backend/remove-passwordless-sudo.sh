#!/bin/bash

# Remove passwordless sudo configuration

SUDOERS_FILE="/etc/sudoers.d/local-network-scanner"

echo "Removing passwordless sudo configuration..."
echo ""

if [ -f "$SUDOERS_FILE" ]; then
    sudo rm "$SUDOERS_FILE"
    echo "✓ Removed ${SUDOERS_FILE}"
    echo ""
    echo "You will now need to enter your password when running with sudo."
else
    echo "No configuration found at ${SUDOERS_FILE}"
fi
