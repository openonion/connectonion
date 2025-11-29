import pytest


def pytest_collection_modifyitems(items):
    """Mark all tests in this folder as real API tests."""
    for item in items:
        # Check if the test is in the real_api directory
        if "real_api" in str(item.fspath):
            item.add_marker(pytest.mark.real_api)
