#!/bin/bash
# Cleanup script for ConnectOnion CLI testing
# Removes global ~/.co folder and test directories

set -e

echo "🧹 Cleaning up test environment..."

# Remove global ~/.co folder
if [ -d "$HOME/.co" ]; then
    echo "  Removing ~/.co"
    rm -rf "$HOME/.co"
fi

# Remove test directories in /tmp
if [ -d "/tmp/connectonion-test" ]; then
    echo "  Removing /tmp/connectonion-test"
    rm -rf /tmp/connectonion-test
fi

echo "✅ Cleanup complete!"