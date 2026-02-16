"""Integration test configuration - auto-applies integration marker to all tests in this folder."""

"""
LLM-Note: Integration tests configuration

What it tests:
- pytestmark: Automatically marks all integration tests with @pytest.mark.integration

Components under test:
- tests/integration/* (all integration test modules)
"""

import pytest

# Automatically mark all tests in this folder as integration tests
pytestmark = pytest.mark.integration
