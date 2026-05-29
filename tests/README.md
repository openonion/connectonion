# ConnectOnion Tests

> Comprehensive testing suite for the ConnectOnion agent framework

---

## 📁 Test Organization

Two layers — **unit** and **e2e**. See [TEST_ORGANIZATION.md](./TEST_ORGANIZATION.md) for full guidance.

```
tests/
├── TEST_ORGANIZATION.md      # Principles and guidance
├── README.md                 # This file
├── conftest.py               # Shared fixtures/markers
├── .env.example              # Template for local test env
├── .env                      # Local test env (gitignored)
│
├── unit/                     # Auto-marked: unit
├── e2e/                      # Auto-marked: e2e
│   ├── real_api/             # Auto-marked: e2e, real_api (needs API keys)
│   ├── cli/                  # Auto-marked: e2e, cli (real `co` invocations)
│   └── manual/               # Demo scripts (not collected)
├── fixtures/                 # Shared test data
└── utils/                    # MockLLM, ProjectHelper, etc.
```

Markers are auto-applied by folder in `tests/conftest.py` — individual test files
don't need `@pytest.mark.unit / e2e / cli / real_api`.

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
# Default: unit + offline e2e (excludes real_api, network)
pytest

# Only unit (fast)
pytest -m unit

# All e2e (cli + real_api + offline workflows)
pytest -m e2e

# Only CLI e2e
pytest -m cli

# Real API tests (requires API keys, costs money)
pytest -m real_api
```

---

## 📊 Test Categories

### Unit (`tests/unit/test_*.py`)
One test file per source file, all dependencies mocked. Fast (<1s each), no API keys.
- `test_agent.py`, `test_llm.py`, `test_tool_factory.py`, `test_console.py`, `test_decorators.py`, etc.

### E2E offline (`tests/e2e/test_*.py`)
End-to-end workflows that don't need real APIs.
- `test_example_agent.py` — full agent run with MockLLM
- `test_relay_e2e.py` — relay protocol against local server
- `test_deploy.py` — deploy flow

### E2E + CLI (`tests/e2e/cli/test_cli_*.py`)
Real `co` CLI invocations. File-system + subprocess.
- `test_cli_init.py`, `test_cli_auth.py`, `test_browser_cli.py`, etc.

### E2E + real_api (`tests/e2e/real_api/test_real_*.py`)
Actual API calls. Slow (5-30s), needs keys, costs money.
- `test_real_openai.py`, `test_real_anthropic.py`, `test_real_gemini.py`, `test_real_email.py`

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

### ProjectHelper Context Manager

Create a temporary ConnectOnion project for testing:

```python
from tests.utils.config_helpers import ProjectHelper

with ProjectHelper() as project_dir:
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
from tests.utils.config_helpers import ProjectHelper

def test_with_project():
    """Test new feature with a temporary project."""
    with ProjectHelper() as project_dir:
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
   - Check `IS_EMAIL_ACTIVE` env var in `~/.co/keys.env`

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
1. Write unit tests first (TDD) — mock external services
2. Add e2e tests if there's a real workflow to verify (real_api gated for cost)
3. Update this README if the test categories change
4. Ensure all tests pass
5. Check coverage remains above 85%

---

Happy Testing! 🧪
