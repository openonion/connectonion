#!/bin/bash
# Deploy ConnectOnion to AWS test server for testing
set -e

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
PROJECT_ROOT="$( cd "$SCRIPT_DIR/../../.." && pwd )"

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
    echo ""
    echo "Please copy your SSH key to:"
    echo "  $SCRIPT_DIR/$TEST_KEY_FILE"
    echo ""
    exit 1
fi

chmod 600 "$KEY_PATH"

echo "🚀 Deploying ConnectOnion to test server..."
echo "   Server: $TEST_SERVER_IP"
echo ""

# Step 1: Build package
echo "📦 Building ConnectOnion package..."
cd "$PROJECT_ROOT"

# Create source distribution
$TEST_PYTHON setup.py sdist > /dev/null 2>&1

# Get the built package name
PACKAGE_FILE=$(ls -t dist/connectonion-*.tar.gz | head -1)
if [ -z "$PACKAGE_FILE" ]; then
    echo "❌ Failed to build package"
    exit 1
fi

PACKAGE_NAME=$(basename "$PACKAGE_FILE")
echo "   ✓ Built: $PACKAGE_NAME"

# Step 2: Create test directory on server
echo ""
echo "📁 Creating test directory on server..."
ssh -i "$KEY_PATH" "$TEST_USER@$TEST_SERVER_IP" "mkdir -p $TEST_DIR" 2>/dev/null || true
echo "   ✓ Directory created: $TEST_DIR"

# Step 3: Upload package
echo ""
echo "📤 Uploading package to server..."
scp -i "$KEY_PATH" "$PACKAGE_FILE" "$TEST_USER@$TEST_SERVER_IP:$TEST_DIR/" > /dev/null 2>&1
echo "   ✓ Package uploaded"

# Step 4: Upload test suite
echo ""
echo "📋 Uploading test suite..."
scp -i "$KEY_PATH" "$PROJECT_ROOT/tests/cli"/*.sh "$TEST_USER@$TEST_SERVER_IP:$TEST_DIR/" > /dev/null 2>&1
echo "   ✓ Test scripts uploaded"

# Step 5: Install package on server
echo ""
echo "🔧 Installing ConnectOnion on server..."
ssh -i "$KEY_PATH" "$TEST_USER@$TEST_SERVER_IP" << EOF
    cd $TEST_DIR

    # Uninstall old version if exists
    pip3 uninstall -y connectonion 2>/dev/null || true

    # Install from package
    pip3 install --user "$PACKAGE_NAME" 2>&1 | grep -v "already satisfied" || true

    # Set execute permissions on test scripts
    chmod +x *.sh 2>/dev/null || true

    # Verify installation
    if command -v co >/dev/null 2>&1; then
        echo "✓ ConnectOnion installed successfully"
    else
        echo "⚠️  Warning: 'co' command not found in PATH"
        echo "   You may need to add ~/.local/bin to PATH"
    fi
EOF

echo ""
echo "✅ Deployment complete!"
echo ""
echo "Next step:"
echo "  ./tests/cli/aws/run-remote-tests.sh"
echo ""
