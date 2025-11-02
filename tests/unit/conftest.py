"""Unit test configuration - auto-applies unit marker to all tests in this folder."""

import pytest

# Automatically mark all tests in this folder as unit tests
pytestmark = pytest.mark.unit
