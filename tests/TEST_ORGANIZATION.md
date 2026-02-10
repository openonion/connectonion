# Test Organization Principles

*Keep simple things simple, make complicated things possible*

## Test Structure: Folder Categories

### 1. Unit Tests (`tests/unit/test_*.py`)
**One test file for each source file** - Test individual components in isolation with all dependencies mocked. Kept fast and deterministic.

**File Mapping Rule**: Each source file gets a corresponding test file
- `connectonion/agent.py` → `tests/unit/test_agent.py`
- `connectonion/llm.py` → `tests/unit/test_llm.py`
- `connectonion/tool_factory.py` → `tests/unit/test_tool_factory.py`
- `connectonion/console.py` → `tests/unit/test_console.py`

**Characteristics**:
- No external dependencies
- All APIs mocked
- Fast execution (<1s per test)
- Can run without API keys

### 2. Integration Tests (`tests/integration/test_*.py`)
Cross-component tests that exercise multiple modules using mocks or local resources (no real external APIs).

**Characteristics**:
- No real API calls
- May touch filesystem or local resources
- Medium speed

### 3. Real API Tests (`tests/real_api/test_real_*.py` and `tests/real_api/test_*.py`)
**Tests that make actual API calls** - Verify integration with external services.

**Examples**:
- `test_real_openai.py` - Test with real OpenAI API
- `test_real_anthropic.py` - Test with real Anthropic API
- `test_real_gemini.py` - Test with real Google Gemini API
- `test_real_email.py` - Actually send/receive emails
- `test_real_example_agent.py` - Full end-to-end example with real APIs

**Characteristics**:
- Requires API keys
- Network dependent
- Slower execution (5-30s per test)
- Costs real money (API usage)

### 4. CLI Tests (`tests/cli/test_cli_*.py`)
**Test command-line interface** - Verify CLI commands work correctly.

**Examples**:
- `test_cli_init.py` - Test `co init` command
- `test_cli_auth.py` - Test `co auth` command
- `test_cli_browser.py` - Test browser automation

**Characteristics**:
- File system operations
- No API calls needed
- Medium speed (1-5s per test)
- Tests user-facing interface

### 5. E2E Tests (`tests/e2e/test_*.py`)
End-to-end workflows that do not require real APIs. Real API E2E flows live under
`tests/real_api/` and are marked `e2e_online`.

## Markers

Markers are applied automatically based on folder names in `tests/conftest.py`:
- `unit`, `integration`, `cli`, `e2e`, `real_api`
Additional markers:
- `e2e_online` for real-API end-to-end workflows

You can still add additional markers like `slow`, `benchmark`, `network`, or `deploy` when needed.

## Decision Tree: Where Does My Test Go?

```
Is it testing a single source file's logic?
  ├─ YES → tests/unit/test_*.py
  └─ NO
      ├─ Does it need real API calls?
      │   ├─ YES → tests/real_api/test_*.py
      │   └─ NO
      │       └─ Is it testing CLI commands?
      │           ├─ YES → tests/cli/test_*.py
      │           └─ NO → tests/integration/test_*.py (or tests/e2e/test_*.py for full workflows)
```

## Running Tests

```bash
# Run unit tests only (fast, no API keys needed)
pytest -m unit

# Run integration tests (no external APIs)
pytest -m integration

# Run CLI tests
pytest -m cli

# Run E2E tests (offline workflows)
pytest -m e2e

# Run real API E2E tests
pytest -m "real_api and e2e_online"

# Run real API tests (requires API keys)
pytest -m real_api

# Run everything except real API tests (for CI without secrets)
pytest -m "not real_api"
```

## File Naming Rules

- `tests/unit/test_*.py` - Unit tests (one per source file)
- `tests/integration/test_*.py` - Integration tests (no external APIs)
- `tests/real_api/test_real_*.py` and `tests/real_api/test_*.py` - Real API tests
- `tests/cli/test_cli_*.py` - CLI tests
- `tests/e2e/test_*.py` - E2E tests (offline workflows)

Use folders for clarity; names still indicate intent.

## Notes

- When in doubt, prefer unit tests over real API tests
- Keep real API tests isolated under `tests/real_api/`
- The example agent tests are split into offline (`tests/e2e/test_example_agent.py`) and real API (`tests/real_api/test_real_example_agent.py`)
