"""E2E test configuration - auto-applies e2e marker to all tests in this folder."""

import pytest

# Automatically mark all tests in this folder as e2e tests
pytestmark = pytest.mark.e2e
