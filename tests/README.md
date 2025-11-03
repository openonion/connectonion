# ConnectOnion Tests

> Comprehensive testing suite for the ConnectOnion agent framework

---

## 📁 Test Organization

Tests are organized into folders with pytest markers (see [TEST_ORGANIZATION.md](./TEST_ORGANIZATION.md)):

```
tests/
├── TEST_ORGANIZATION.md      # Principles and guidance
├── README.md                 # This file
├── conftest.py               # Shared fixtures/markers
├── .env.example              # Template for local test env
├── .env                      # Local test env (gitignored)
│
├── unit/                     # Unit tests (auto-marked: unit)
├── integration/              # Integration tests (auto-marked: integration)
├── cli/                      # CLI tests (auto-marked: cli)
├── e2e/                      # End-to-end tests (auto-marked: e2e)
└── real_api/                 # Real API tests (auto-marked: real_api)
```

---

## 🚀 Quick Start

### 1. Set Up Environment

```bash
# Install dependencies
pip install -r requirements.txt

# Copy .env.example to .env and add your API keys (optional)
cp tests/.env.example tests/.env
# Edit tests/.env and add your API keys

# Notes:
# - real_api tests are excluded by default via pytest.ini addopts
# - enable them by running with: pytest -m real_api
```

### 2. Run Tests by Category

```bash
# Unit tests (fast)
pytest -m unit

# Integration tests (no external APIs)
pytest -m integration

# CLI tests
pytest -m cli

# End-to-end example
pytest -m e2e

# Real API tests (requires API keys)
pytest -m real_api

# Everything except real API (default in CI)
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
from tests.utils.config_helpers import TestProject

with TestProject() as project_dir:
    # Test code here - project is automatically cleaned up
    from connectonion import send_email, get_emails
    
    emails = get_emails()
    print(f"Found {len(emails)} emails")
```

### Sample Test Data

Use predefined test emails:

```python
from tests.utils.config_helpers import SAMPLE_EMAILS

for email in SAMPLE_EMAILS:
    print(f"Test email: {email['subject']}")
```

---

## 📝 Writing New Tests

### Pytest Template for New Test

```python
from tests.utils.config_helpers import TestProject

def test_with_project():
    """Test new feature with a temporary project."""
    with TestProject() as project_dir:
        from connectonion import your_function
        result = your_function()
        assert result
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
# Verbose output, print stdout/stderr, show logs
pytest -vvvs
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

CI runs on pull requests and pushes to main:
- Installs dependencies
- Runs `pytest -m "not real_api"`
- Reports durations and failures

See `.github/workflows/tests.yml` for CI configuration.

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
