#!/bin/bash
# Test Star for Credits flow (Issue #28) - MANUAL TEST
# This tests the flow: co init -> Star for $1 credit -> minimal template

set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

echo "🧪 Testing Star for Credits Flow (Issue #28) - MANUAL TEST"
echo "==========================================================="

# Clean up first
bash "$SCRIPT_DIR/cleanup.sh"

# Create test directory in /tmp
mkdir -p /tmp/connectonion-test
cd /tmp/connectonion-test

echo ""
echo "⚠️  This is a MANUAL INTERACTIVE test"
echo ""
echo "📝 Test scenario:"
echo "  1. Run 'co init' (will start now)"
echo "  2. When prompted, choose: ⭐ Star for \$1 OpenOnion credit"
echo "  3. GitHub will open in browser - star the repo"
echo "  4. Return here and answer 'y' when asked if you starred"
echo "  5. When prompted, choose template: minimal"
echo ""
echo "Expected result:"
echo "  ✅ Should NOT see 'agent_email referenced before assignment' error"
echo "  ✅ Should successfully authenticate and get credits"
echo "  ✅ Should create .env with AGENT_EMAIL"
echo ""

read -p "Press Enter to start the interactive test..."

# Run co init (interactive - user must select star option)
co init

EXIT_CODE=$?

echo ""
if [ $EXIT_CODE -eq 0 ]; then
    echo "✅ Test PASSED!"
    echo "   No 'agent_email referenced before assignment' error detected"

    # Check if .env was created with AGENT_EMAIL
    if [ -f ".env" ]; then
        if grep -q "AGENT_EMAIL=" .env; then
            echo "   ✓ AGENT_EMAIL found in .env"
        else
            echo "   ⚠️  Warning: AGENT_EMAIL not found in .env"
        fi

        if grep -q "OPENONION_API_KEY=" .env; then
            echo "   ✓ OPENONION_API_KEY found in .env"
        fi
    else
        echo "   ⚠️  Warning: .env file not found"
    fi
else
    echo "❌ Test FAILED!"
    echo "   Command exited with code: $EXIT_CODE"
    echo "   Check the output above for errors"
fi

exit $EXIT_CODE