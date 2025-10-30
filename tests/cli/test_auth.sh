#!/bin/bash
# Test co auth command (Issue #28)
# This tests the flow: co auth after initialization

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🧪 Testing 'co auth' Command"
echo "============================="

# Clean up first
bash "$SCRIPT_DIR/cleanup.sh"

# First initialize ConnectOnion to create keys
echo ""
echo "Step 1: Initialize ConnectOnion (will create ~/.co)"
echo ""

# Create test directory in /tmp
mkdir -p /tmp/connectonion-test
cd /tmp/connectonion-test

# Run co init with --yes flag to skip prompts
echo "Running: co init --yes --template minimal"
co init --yes --template minimal

echo ""
echo "Step 2: Test 'co auth' command"
echo ""
echo "Expected: Should NOT see 'agent_email referenced before assignment' error"
echo ""

# Run co auth
echo "Running: co auth"
co auth

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Test PASSED!"
    echo "   No 'agent_email referenced before assignment' error detected"
    echo "   Authentication completed successfully"

    # Check if .env was created with AGENT_EMAIL
    if [ -f ".env" ]; then
        if grep -q "AGENT_EMAIL=" .env; then
            echo "   ✓ AGENT_EMAIL found in .env"
        else
            echo "   ⚠️  Warning: AGENT_EMAIL not found in .env"
        fi
    fi
else
    echo "❌ Test FAILED!"
    echo "   Command exited with code: $EXIT_CODE"
    echo "   Check the output above for errors"
fi

exit $EXIT_CODE
