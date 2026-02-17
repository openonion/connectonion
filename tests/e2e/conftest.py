"""E2E test configuration - auto-applies e2e marker to all tests in this folder."""

"""
LLM-Note: E2E tests configuration

What it tests:
- pytestmark: Automatically marks all e2e tests with @pytest.mark.e2e

Components under test:
- tests/e2e/* (all end-to-end test modules)
"""

import pytest

# Automatically mark all tests in this folder as e2e tests
pytestmark = pytest.mark.e2e
