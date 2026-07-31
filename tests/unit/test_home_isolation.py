"""The test suite must not be able to reach the operator's real ~/.co.

This is not hypothetical. `tests/e2e/cli/test_cli_auth_microsoft.py` ran
`co auth microsoft` against mocked HTTP inside `CliRunner.isolated_filesystem()`,
which isolates the working directory and nothing else — so the fake credentials
it asserts on were also written to the real `~/.co/keys.env`, replacing a live
Outlook session with `access_token='eyJ0eXAi.test'`.

It surfaced days later as "Microsoft session expired, reconnect with
co auth microsoft", which is the last thing anyone would trace back to a test.
"""

import os
from pathlib import Path


SANDBOX_PREFIXES = ("/private/", "/tmp", "/var", "C:\\Users\\RUNNER")


class TestTheRealHomeIsOutOfReach:
    def test_the_home_env_var_is_a_sandbox(self):
        """$HOME is what the shell-facing paths resolve against."""
        assert os.environ["HOME"].startswith(SANDBOX_PREFIXES), os.environ["HOME"]

    def test_path_home_is_redirected_too(self):
        """Commands resolve ~/.co through Path.home(), which reads $HOME only on
        some platforms — so it is patched directly as well."""
        assert str(Path.home()).startswith(SANDBOX_PREFIXES), str(Path.home())

    def test_agent_config_path_points_inside_it(self):
        """The other way a command finds the global directory."""
        assert os.environ["AGENT_CONFIG_PATH"].startswith(str(Path.home()))

    def test_writing_the_global_keys_file_lands_in_the_sandbox(self):
        keys = Path(os.environ["AGENT_CONFIG_PATH"]) / "keys.env"
        keys.parent.mkdir(parents=True, exist_ok=True)
        keys.write_text("MICROSOFT_ACCESS_TOKEN=would-have-clobbered-a-real-one\n")

        assert keys.exists()
        assert not str(keys).startswith("/Users/"), str(keys)
