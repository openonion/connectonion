# ConnectOnion Tests

> Comprehensive testing suite for ConnectOnion email functionality

---

## 📁 Test Structure

```
tests/
├── .env.test              # Test credentials (DO NOT use in production)
├── test_config.py         # Fixed test account configuration
├── test_email_functions.py # Unit tests for email functions
├── test_email_integration.py # Integration tests
├── test_email_live.py     # Live backend tests
├── test_curl_emails.sh    # curl-based API tests
└── README.md             # This file
```

---

## 🔑 Test Account

All tests use a **fixed test account** for consistency:

- **Email**: `0x04e1c4ae@mail.openonion.ai`
- **Public Key**: `04e1c4ae3c57d716383153479dae869e51e86d43d88db8dfa22fba7533f3968d`
- **Short Address**: `0x04e1c4ae`

This account is configured in `test_config.py` and used across all tests.

---

## 🚀 Quick Start

### 1. Set Up Environment

```bash
# Copy test environment file
cp .env.test .env

# Add your real API keys (never commit these!)
export OPENAI_API_KEY=your-real-key-here
```

### 2. Run Tests

```bash
# Run all tests
python -m pytest tests/ -v

# Run specific test file
python -m pytest tests/test_email_functions.py -v

# Run with coverage
python -m pytest tests/ --cov=connectonion --cov-report=html
```

### 3. Test with Live Backend

```bash
# Test with deployed backend
python tests/test_email_live.py --confirm

# Test with local backend
CONNECTONION_BACKEND_URL=http://localhost:8000 python tests/test_email_live.py --confirm
```

---

## 📊 Test Categories

### Unit Tests (`test_email_functions.py`)
Tests individual functions in isolation using mocks:
- `send_email()` - 5 tests
- `get_emails()` - 5 tests  
- `mark_read()` - 5 tests
- Helper functions - 4 tests

**Run**: `python -m pytest tests/test_email_functions.py`

### Integration Tests (`test_email_integration.py`)
Tests with a simulated ConnectOnion project:
- Project setup with test account
- Email flow simulation
- Configuration handling

**Run**: `python -m pytest tests/test_email_integration.py`

### Live Backend Tests (`test_email_live.py`)
Tests against the deployed backend:
- Real email sending
- Inbox retrieval
- Mark as read functionality

**Run**: `python tests/test_email_live.py --confirm`

---

## 🧪 Testing with curl

Use the provided shell script to test API endpoints directly:

```bash
# Set JWT token from test account
export CONNECTONION_JWT_TOKEN=$(grep TEST_JWT_TOKEN .env.test | cut -d= -f2)

# Run curl tests
bash test_curl_emails.sh
```

### Individual curl Commands

```bash
# Get all emails
curl -X GET "https://oo.openonion.ai/api/emails" \
  -H "Authorization: Bearer $CONNECTONION_JWT_TOKEN" \
  -H "Content-Type: application/json" | jq '.'

# Get unread emails only
curl -X GET "https://oo.openonion.ai/api/emails?unread_only=true" \
  -H "Authorization: Bearer $CONNECTONION_JWT_TOKEN" \
  -H "Content-Type: application/json" | jq '.'

# Get last 5 emails
curl -X GET "https://oo.openonion.ai/api/emails?limit=5" \
  -H "Authorization: Bearer $CONNECTONION_JWT_TOKEN" \
  -H "Content-Type: application/json" | jq '.'

# Mark emails as read
curl -X POST "https://oo.openonion.ai/api/emails/mark-read" \
  -H "Authorization: Bearer $CONNECTONION_JWT_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"email_ids": ["msg_123", "msg_124"]}' | jq '.'
```

---

## 🔧 Test Utilities

### TestProject Context Manager

Create a temporary ConnectOnion project for testing:

```python
from tests.test_config import TestProject

with TestProject() as project_dir:
    # Test code here - project is automatically cleaned up
    from connectonion import send_email, get_emails
    
    emails = get_emails()
    print(f"Found {len(emails)} emails")
```

### Sample Test Data

Use predefined test emails:

```python
from tests.test_config import SAMPLE_EMAILS

for email in SAMPLE_EMAILS:
    print(f"Test email: {email['subject']}")
```

---

## 📝 Writing New Tests

### Template for New Test

```python
import unittest
from tests.test_config import TEST_ACCOUNT, TestProject

class TestNewFeature(unittest.TestCase):
    def test_with_project(self):
        """Test new feature with test project."""
        with TestProject() as project_dir:
            # Your test code here
            from connectonion import your_function
            
            result = your_function()
            self.assertTrue(result)
```

### Mocking Best Practices

```python
from unittest.mock import patch, MagicMock

@patch('requests.post')
def test_api_call(self, mock_post):
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.return_value = {"success": True}
    mock_post.return_value = mock_response
    
    # Your test code
```

---

## 🔐 Security Notes

### ⚠️ IMPORTANT
- **NEVER** commit real API keys to version control
- The `.env.test` file contains TEST ONLY credentials
- Always use environment variables for real keys
- Rotate test tokens periodically

### Safe Testing Pattern

```python
import os

# Use environment variable with fallback to test value
api_key = os.getenv('OPENAI_API_KEY', 'test-key-for-mocking')

# Check if we have real credentials
if api_key.startswith('sk-'):
    # Real key - can test with live API
    pass
else:
    # Test key - use mocks
    pass
```

---

## 🐛 Troubleshooting

### Common Issues

1. **"Email not activated"**
   - Run `co auth` to activate email
   - Check `email_active` in `.co/config.toml`

2. **"No JWT token"**
   - Set `CONNECTONION_JWT_TOKEN` environment variable
   - Or use the test token from `.env.test`

3. **"Backend not available"**
   - Check backend URL: `https://oo.openonion.ai`
   - For local: start with `python main.py` in oo-api/

4. **Tests failing with mocks**
   - Ensure you're using `@patch` decorators correctly
   - Check import paths match actual module structure

### Debug Mode

```bash
# Run tests with verbose output
python -m pytest tests/ -vvs

# Run with debug logging
TEST_VERBOSE=true python tests/test_email_live.py
```

---

## 📈 Test Coverage

Check test coverage:

```bash
# Generate coverage report
python -m pytest tests/ --cov=connectonion --cov-report=term-missing

# Generate HTML report
python -m pytest tests/ --cov=connectonion --cov-report=html
# Open htmlcov/index.html in browser
```

Current coverage targets:
- `send_email`: 90%+
- `get_emails`: 90%+
- `mark_read`: 85%+

---

## 🔄 Continuous Integration

Tests run automatically on:
- Pull requests
- Commits to main branch
- Nightly builds

See `.github/workflows/test.yml` for CI configuration.

---

## 📚 Resources

- [ConnectOnion Documentation](https://github.com/wu-changxing/connectonion)
- [Email API Documentation](../docs/get_emails.md)
- [Backend API Reference](../../oo-api/README.md)

---

## 🤝 Contributing

When adding new email features:
1. Write unit tests first (TDD)
2. Add integration tests
3. Update this README
4. Ensure all tests pass
5. Check coverage remains above 85%

---

Happy Testing! 🧪