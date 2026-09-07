"""The opt-in Claude release gate must not turn provider failures green."""

import os

import pytest

from tests import conftest as root_conftest
from tests.e2e.real_api.test_real_claude_code import (
    _real_claude_auth_environment,
    _require_success,
)


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


def test_default_macos_auth_keeps_the_keychain_context():
    assert _real_claude_auth_environment("darwin", "/operator", None) == {
        "HOME": "/operator"
    }


@pytest.mark.parametrize("platform", ["linux", "win32"])
def test_default_file_auth_uses_only_the_claude_directory(platform):
    assert _real_claude_auth_environment(platform, "/operator", None) == {
        "CLAUDE_CONFIG_DIR": os.path.join("/operator", ".claude")
    }


def test_explicit_claude_config_wins_on_every_platform():
    assert _real_claude_auth_environment(
        "darwin", "/operator", "/accounts/work"
    ) == {"CLAUDE_CONFIG_DIR": "/accounts/work"}
