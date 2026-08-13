"""The opt-in Claude release gate must not turn provider failures green."""

import pytest

from tests import conftest as root_conftest
from tests.e2e.real_api.test_real_claude_code import _require_success


def test_completed_real_claude_result_passes():
    assert _require_success({"status": "completed"}) is None


def test_stale_claude_auth_fails_instead_of_skipping():
    error = "401 OAuth access token has expired. Re-authenticate to continue."

    with pytest.raises(pytest.fail.Exception, match="OAuth access token has expired"):
        _require_success({"status": "error", "error": error})


def test_only_environment_key_tests_need_the_global_auth_skip():
    class Item:
        def __init__(self, *markers):
            self.keywords = dict.fromkeys(markers, True)

    assert root_conftest._needs_environment_api_key(Item("real_api")) is True
    assert root_conftest._needs_environment_api_key(
        Item("real_api", "provider_cli")
    ) is False
