#!/bin/bash

# Run the email agent test suite

echo "🚀 Running Email Agent Tests"
echo "============================"
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "Creating .env file with default test email..."
    echo "TEST_TO_EMAIL_ADDR=yingxiaohao@outlook.com" > .env
fi

# Display test configuration
echo "📧 Test Configuration:"
echo "----------------------"
cat .env
echo ""

# Run the test
python test_agent.py

# Check exit code
if [ $? -eq 0 ]; then
    echo ""
    echo "✅ All tests passed!"
else
    echo ""
    echo "❌ Tests failed. Please check the output above."
    exit 1
fi