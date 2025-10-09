# Test Organization Principles

*Keep simple things simple, make complicated things possible*

## Test Structure: Folder Categories

### 1. Unit Tests (`tests/unit/test_*.py`)
**One test file for each source file** - Test individual components in isolation with all dependencies mocked. Kept fast and deterministic.

**File Mapping Rule**: Each source file gets a corresponding test file
- `connectonion/agent.py` → `tests/test_agent.py`
- `connectonion/llm.py` → `tests/test_llm.py`
- `connectonion/tool_factory.py` → `tests/test_tool_factory.py`
- `connectonion/console.py` → `tests/test_console.py`

**Characteristics**:
- No external dependencies
- All APIs mocked
- Fast execution (<1s per test)
- Can run without API keys

### 2. Real API Tests (`tests/real_api/test_real_*.py` and `tests/real_api/test_*.py`)
**Tests that make actual API calls** - Verify integration with external services.

**Examples**:
- `test_real_openai.py` - Test with real OpenAI API
- `test_real_anthropic.py` - Test with real Anthropic API
- `test_real_gemini.py` - Test with real Google Gemini API
- `test_real_email.py` - Actually send/receive emails
- `test_real_auth.py` - Real authentication flow

**Characteristics**:
- Requires API keys
- Network dependent
- Slower execution (5-30s per test)
- Costs real money (API usage)

### 3. CLI Tests (`tests/cli/test_cli_*.py`)
**Test command-line interface** - Verify CLI commands work correctly.

**Examples**:
- `test_cli_init.py` - Test `co init` command
- `test_cli_auth.py` - Test `co auth` command
- `test_cli_browser.py` - Test browser automation
- `test_cli_xray.py` - Test debugging commands

**Characteristics**:
- File system operations
- No API calls needed
- Medium speed (1-5s per test)
- Tests user-facing interface

### 4. Example Agent Test (`tests/e2e/test_example_agent.py`)
**A complete, working agent** - Living documentation that tests everything end-to-end.

### 5. Integration Tests (`tests/integration/test_*.py`)
Cross-component tests that exercise multiple modules using mocks or local resources (no real external APIs).

This is a special test that:
- Creates a real agent with multiple tools
- Performs actual tasks
- Uses all major features (debug, logging, tools, history)
- Shows best practices for using the framework
- Acts as both a test and example code

## Decision Tree: Where Does My Test Go?

```
Is it testing a single source file's logic?
  ├─ YES → test_*.py (unit test)
  └─ NO
      ├─ Does it need real API calls?
      │   ├─ YES → test_real_*.py
      │   └─ NO
      │       └─ Is it testing CLI commands?
      │           ├─ YES → test_cli_*.py
      │           └─ NO → test_example_agent.py (full workflow)
```

## Running Tests

```bash
# Run unit tests only (fast, no API keys needed)
pytest tests/unit

# Run real API tests (requires API keys)
pytest tests/real_api -m real_api

# Run CLI tests
pytest tests/cli -m cli

# Run the complete example agent
pytest tests/e2e/test_example_agent.py

# Run integration + unit + CLI (skip real API)
pytest -m "not real_api"

# Run everything except real API tests (for CI without secrets)
pytest -m "not real_api"
```

## Writing New Tests

### Unit Test Template
```python
# test_mymodule.py
"""Unit tests for mymodule.py"""

from unittest.mock import Mock, patch
from connectonion.mymodule import MyClass

def test_my_function():
    """Test specific function behavior."""
    # Arrange
    mock_dependency = Mock()

    # Act
    result = my_function(mock_dependency)

    # Assert
    assert result == expected_value
```

### Real API Test Template
```python
# test_real_provider.py
"""Real API tests for provider integration."""

import pytest
import os

@pytest.mark.real_api
@pytest.mark.skipif(not os.getenv("PROVIDER_API_KEY"), reason="No API key")
def test_real_api_call():
    """Test actual API integration."""
    # This will make real API calls
    agent = Agent("test")
    response = agent.input("Hello")
    assert response.content
```

### CLI Test Template
```python
# test_cli_command.py
"""Test CLI command."""

from click.testing import CliRunner
from connectonion.cli.main import cli

def test_command():
    """Test CLI command execution."""
    runner = CliRunner()
    with runner.isolated_filesystem():
        result = runner.invoke(cli, ['command', '--flag'])
        assert result.exit_code == 0
        assert "expected output" in result.output
```

## Test Markers

```python
@pytest.mark.real_api   # Requires real API keys
@pytest.mark.slow       # Takes >10 seconds
@pytest.mark.cli        # CLI-specific test
```

## Philosophy

1. **Mirror the source** - Test structure follows code structure
2. **Clear boundaries** - Obvious what each test type does
3. **No ambiguity** - Easy to know where to add new tests
4. **Fast feedback** - Unit tests run quickly for rapid development
5. **Real validation** - Real API tests ensure it actually works

## File Naming Rules

- `tests/unit/test_*.py` - Unit tests (one per source file)
- `tests/integration/test_*.py` - Integration tests (no external APIs)
- `tests/real_api/test_real_*.py` and `tests/real_api/test_*.py` - Real API tests
- `tests/cli/test_cli_*.py` - CLI tests
- `tests/e2e/test_example_agent.py` - The one complete example

Use folders for clarity; names still indicate intent.

## Current Test Migration

Files were organized into folders (unit, real_api, cli, e2e). Non-pytest, print-based helper scripts have been parked under `tests/real_api/manual/` and excluded from pytest discovery.

## Notes

- Keep test files flat in `tests/` directory - no subdirectories needed
- The naming convention IS the organization
- When in doubt, prefer unit tests over real tests
- The example agent test is special - it's both documentation and validation
## Organization Status - Updated

### ✅ Unit Tests (test_*.py)
- `test_agent.py` - Agent core functionality
- `test_agent_prompts.py` - Agent prompt handling  
- `test_decorators.py` - Decorator functions
- `test_llm.py` - LLM interface
- `test_llm_do.py` - LLM do function
- `test_openonion_llm.py` - OpenOnion LLM implementation
- `test_prompts.py` - Prompt utilities
- `test_tool_factory.py` - Tool creation from functions
- `test_console.py` - Console output functions
- `test_tool_executor.py` - Tool execution
- `test_history.py` - Behavior history tracking
- `test_address.py` - Address generation/validation
- `test_email_functions.py` - Email function logic
- `test_config.py` - Configuration utilities
- `test_xray_auto_trace.py` - X-ray auto tracing
- `test_xray_class.py` - X-ray class decorator
- `test_xray_without_decorator.py` - X-ray without decorator

### ✅ Real API Tests (test_real_*.py)
- `test_real_openai.py` - OpenAI API integration
- `test_real_anthropic.py` - Anthropic API integration
- `test_real_gemini.py` - Google Gemini API integration
- `test_real_managed.py` - Managed keys/proxy
- `test_real_api.py` - General API tests
- `test_real_auth.py` - Authentication flow
- `test_real_email.py` - Email functionality with live backend
- `test_real_multi_llm.py` - Multi-LLM model support

### ✅ CLI Tests (test_cli_*.py)
- `test_cli.py` - General CLI commands
- `test_cli_init.py` - co init command
- `test_cli_create.py` - co create command
- `test_cli_browser.py` - Browser automation

### ✅ Example Agent
- `test_example_agent.py` - Complete working example

### 🗑️ Removed Files
Temporary/obsolete tests removed during organization:
- `test_input_method_migration.py` (migration complete)
- `test_final_verification.py` (temporary verification)
- `test_our_fixes.py` (temporary fixes verification)
- `agent.py` (not a test file)
- `test_email_complete.py` (duplicate)
- `test_email_integration.py` (duplicate)
- `test_co_o4mini.py` (outdated script)
- `test_email_live.py` → renamed to `test_real_email.py`
- `test_multi_llm.py` → renamed to `test_real_multi_llm.py`

**Organization Complete!** All tests now follow the folder system.
