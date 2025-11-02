"""Integration test configuration - auto-applies integration marker to all tests in this folder."""

import pytest

# Automatically mark all tests in this folder as integration tests
pytestmark = pytest.mark.integration
