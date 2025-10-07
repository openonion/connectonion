#!/bin/bash
# Test BYO API key flow (Issue #29)
# This tests the flow: co init --key <API_KEY> --template minimal

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🧪 Testing BYO API Key Flow (Issue #29)"
echo "========================================"

# Check if API key is provided as argument
if [ -z "$1" ]; then
    echo ""
    echo "❌ Error: OpenAI API key required"
    echo ""
    echo "Usage: $0 <OPENAI_API_KEY>"
    echo ""
    echo "Example:"
    echo "  $0 sk-proj-xxxxx"
    echo ""
    exit 1
fi

API_KEY="$1"

# Clean up first
bash "$SCRIPT_DIR/cleanup.sh"

# Create test directory in /tmp
mkdir -p /tmp/connectonion-test
cd /tmp/connectonion-test

echo ""
echo "📝 Test scenario:"
echo "  Running: co init --key <API_KEY> --template minimal"
echo ""
echo "Expected: Should NOT see 'agent_email referenced before assignment' error"
echo ""

# Run co init with parameters (non-interactive)
echo "Running: co init --key '***' --template minimal"
co init --key "$API_KEY" --template minimal

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Test PASSED!"
    echo "   No 'agent_email referenced before assignment' error detected"
    echo "   Authentication completed successfully"
else
    echo "❌ Test FAILED!"
    echo "   Command exited with code: $EXIT_CODE"
    echo "   Check the output above for errors"
fi

exit $EXIT_CODE