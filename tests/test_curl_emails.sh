#!/bin/bash
# Test email API endpoints with curl

# Configuration - uses environment variables for security
BACKEND_URL="${CONNECTONION_BACKEND_URL:-https://oo.openonion.ai}"
JWT_TOKEN="${CONNECTONION_JWT_TOKEN:-}"

echo "🧪 Testing Email API with curl"
echo "=================================="
echo "Backend: $BACKEND_URL"
echo ""

# Function to check if we have a token
check_auth() {
    if [ -z "$JWT_TOKEN" ]; then
        echo "⚠️  No JWT token found."
        echo "   Please set CONNECTONION_JWT_TOKEN environment variable"
        echo "   You can get a token by running: co auth"
        return 1
    fi
    return 0
}

# Test 1: Health check
echo "1️⃣  Testing health endpoint..."
curl -s "${BACKEND_URL}/health" | jq '.' || echo "❌ Health check failed"
echo ""

# Test 2: Get emails (requires authentication)
echo "2️⃣  Getting emails from inbox..."
if check_auth; then
    response=$(curl -s -X GET "${BACKEND_URL}/api/emails" \
        -H "Authorization: Bearer ${JWT_TOKEN}" \
        -H "Content-Type: application/json")
    
    if [ $? -eq 0 ]; then
        echo "$response" | jq '.' 2>/dev/null || echo "$response"
    else
        echo "❌ Failed to get emails"
    fi
fi
echo ""

# Test 3: Get unread emails only
echo "3️⃣  Getting unread emails..."
if check_auth; then
    curl -s -X GET "${BACKEND_URL}/api/emails?unread_only=true" \
        -H "Authorization: Bearer ${JWT_TOKEN}" \
        -H "Content-Type: application/json" | jq '.'
fi
echo ""

# Test 4: Get limited number of emails
echo "4️⃣  Getting last 5 emails..."
if check_auth; then
    curl -s -X GET "${BACKEND_URL}/api/emails?limit=5" \
        -H "Authorization: Bearer ${JWT_TOKEN}" \
        -H "Content-Type: application/json" | jq '.'
fi
echo ""

# Test 5: Mark email as read (example with placeholder ID)
echo "5️⃣  Example: Mark email as read..."
if check_auth; then
    echo "curl -X POST '${BACKEND_URL}/api/emails/mark-read' \\"
    echo "  -H 'Authorization: Bearer \${JWT_TOKEN}' \\"
    echo "  -H 'Content-Type: application/json' \\"
    echo "  -d '{\"email_ids\": [\"msg_123\"]}'"
    echo ""
    echo "Replace 'msg_123' with actual email ID from your inbox"
fi

echo ""
echo "=================================="
echo "✅ Test script complete"
echo ""
echo "📝 To use this script:"
echo "   1. Get a JWT token: co auth"
echo "   2. Set environment variable: export CONNECTONION_JWT_TOKEN=your-token"
echo "   3. Run: bash test_curl_emails.sh"