"""Unit test configuration - auto-applies unit marker to all tests in this folder."""
"""
LLM-Note: Unit tests configuration

What it tests:
- pytestmark auto-marking

Components under test:
- tests/unit/* config
"""


import pytest

# Automatically mark all tests in this folder as unit tests
pytestmark = pytest.mark.unit
