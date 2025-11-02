# ConnectOnion Tests

> Comprehensive testing suite for the ConnectOnion agent framework

---

## 📁 Test Organization

Tests are organized into 4 clear categories following the principles in [TEST_ORGANIZATION.md](./TEST_ORGANIZATION.md):

```
tests/
├── TEST_ORGANIZATION.md    # Test organization principles
├── README.md               # This file
├── conftest.py            # Shared pytest fixtures
├── .env.test              # Test credentials (DO NOT use in production)
│
├── test_*.py              # Unit tests (one per source file)
├── test_real_*.py         # Real API tests (requires API keys)
├── test_cli_*.py          # CLI command tests
└── test_example_agent.py  # Complete working agent example
```

---

## 🚀 Quick Start

### 1. Set Up Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API keys
cp tests/.env.example tests/.env
# Edit tests/.env and add your API keys

# Tests will auto-skip real_api tests if no API keys are found
```

### 2. Run Tests by Category

```bash
# Run unit tests only (fast, no API keys needed)
pytest test_*.py --ignore=test_real_* --ignore=test_cli_* --ignore=test_example_*

# Run real API tests (requires API keys)
pytest test_real_*.py

# Run CLI tests
pytest test_cli_*.py

# Run the complete example agent
pytest test_example_agent.py

# Run everything except real API tests (for CI)
pytest -m "not real_api"
```

---

## 📊 Test Categories

### 1. Unit Tests (`test_*.py`)
One test file for each source file, all dependencies mocked:
- `test_agent.py` - Agent class logic
- `test_llm.py` - LLM interface
- `test_tool_factory.py` - Tool creation
- `test_console.py` - Debug/logging output
- `test_decorators.py` - xray/replay decorators

**Characteristics**: Fast (<1s), no external dependencies, can run without API keys

### 2. Real API Tests (`test_real_*.py`)
Tests that make actual API calls:
- `test_real_openai.py` - Real OpenAI API
- `test_real_anthropic.py` - Real Anthropic API
- `test_real_gemini.py` - Real Google Gemini API
- `test_real_email.py` - Actually send/receive emails

**Characteristics**: Slow (5-30s), requires API keys, costs real money

### 3. CLI Tests (`test_cli_*.py`)
Test command-line interface:
- `test_cli_init.py` - Project initialization
- `test_cli_auth.py` - Authentication commands
- `test_cli_browser.py` - Browser automation

**Characteristics**: Medium speed (1-5s), file system operations

### 4. Example Agent (`test_example_agent.py`)
A complete working agent that serves as both test and documentation, demonstrating all features in real use

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

- [ConnectOnion Documentation](https://github.com/openonion/connectonion)
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