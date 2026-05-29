"""
LLM-Note: CLI tests configuration

What it tests:
- pytestmark: Automatically marks all CLI tests with @pytest.mark.cli

Components under test:
- tests/cli/* (all CLI test modules)
"""

import pytest

# Mark all tests in this folder as CLI tests
pytestmark = pytest.mark.cli

