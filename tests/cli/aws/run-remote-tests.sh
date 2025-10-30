#!/bin/bash
# Run ConnectOnion tests on AWS test server
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"

# Load configuration
if [ ! -f "$SCRIPT_DIR/config.sh" ]; then
    echo "❌ Error: config.sh not found!"
    echo ""
    echo "Please create config.sh from the template:"
    echo "  cp $SCRIPT_DIR/config.sh.example $SCRIPT_DIR/config.sh"
    echo "  # Then edit config.sh with your server details"
    echo ""
    exit 1
fi

source "$SCRIPT_DIR/config.sh"

# Verify SSH key exists
KEY_PATH="$SCRIPT_DIR/$TEST_KEY_FILE"
if [ ! -f "$KEY_PATH" ]; then
    echo "❌ Error: SSH key not found at $KEY_PATH"
    exit 1
fi

chmod 600 "$KEY_PATH"

echo "🧪 Running ConnectOnion tests on remote server..."
echo "   Server: $TEST_SERVER_IP"
echo ""

# Run tests on remote server
ssh -i "$KEY_PATH" "$TEST_USER@$TEST_SERVER_IP" << 'ENDSSH'
    set -e

    # Add ~/.local/bin to PATH for pip-installed packages
    export PATH="$HOME/.local/bin:$PATH"

    echo "🧹 Cleaning test environment..."

    # Remove global ~/.co folder
    if [ -d "$HOME/.co" ]; then
        echo "   Removing ~/.co"
        rm -rf "$HOME/.co"
    fi

    # Remove test directories
    if [ -d "/tmp/connectonion-test" ]; then
        echo "   Removing /tmp/connectonion-test"
        rm -rf /tmp/connectonion-test"
    fi

    echo "   ✓ Environment cleaned"
    echo ""

    # Change to test directory
    cd ~/connectonion-test

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Running: test_auth.sh"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo ""

    # Run test_auth.sh
    bash test_auth.sh

    EXIT_CODE=$?

    echo ""
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [ $EXIT_CODE -eq 0 ]; then
        echo "✅ Remote tests PASSED"
    else
        echo "❌ Remote tests FAILED (exit code: $EXIT_CODE)"
    fi
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    exit $EXIT_CODE
ENDSSH

TEST_EXIT_CODE=$?

echo ""
if [ $TEST_EXIT_CODE -eq 0 ]; then
    echo "✅ All tests passed on remote server!"
else
    echo "❌ Tests failed on remote server (exit code: $TEST_EXIT_CODE)"
    echo ""
    echo "To debug, SSH to the server:"
    echo "  ssh -i $KEY_PATH $TEST_USER@$TEST_SERVER_IP"
    echo "  cd ~/connectonion-test"
    echo "  cat /tmp/connectonion-test/.env"
fi

exit $TEST_EXIT_CODE
