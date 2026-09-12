"""A project must work on a machine other than the one that made it.

`AGENT_CONFIG_PATH` was written as an absolute path — `/Users/changxing/.co` —
into the global keys.env, which `co create` copies wholesale into every new
project's `.env`. Deploy that project, clone it, or hand it to a colleague, and
the variable names a home directory that does not exist there. Six tools build
their keys.env path from it, and every one of them then looks for credentials
somewhere they can never be. openonion/connectonion#438
"""

import os
from pathlib import Path

import pytest


class TestNothingWritesTheMachinesOwnPath:
    @pytest.mark.parametrize("module", [
        "connectonion/cli/commands/create.py",
        "connectonion/cli/commands/init.py",
        "connectonion/cli/commands/auth_commands.py",
    ])
    def test_no_absolute_config_path_is_written(self, module):
        source = (Path(__file__).parent.parent.parent / module).read_text()

        assert "AGENT_CONFIG_PATH={Path.home()" not in source
        assert "AGENT_CONFIG_PATH={co_dir}" not in source

    def test_it_is_not_treated_as_an_identity_key(self):
        """`co init` copies identity keys from the global file into the project.
        A path describes the machine, not the identity."""
        from connectonion.cli.commands import init

        source = (Path(init.__file__)).read_text()
        block = source[source.index("IDENTITY_KEYS"):source.index("IDENTITY_KEYS") + 200]

        assert "AGENT_CONFIG_PATH" not in block


class TestTheDefaultIsEnough:
    """Removing the variable is only safe because every reader already has the
    right fallback — and they must keep having it."""

    @pytest.mark.parametrize("provider", ["google", "microsoft"])
    def test_credentials_follow_the_machine_home(self, provider, monkeypatch):
        from connectonion.environment import provider_keys, global_config_dir
        from connectonion.provider_credentials import resolve_provider_credentials
        monkeypatch.delenv("AGENT_CONFIG_PATH", raising=False)
        for key in provider_keys(provider):
            monkeypatch.delenv(key, raising=False)
        config = global_config_dir()
        config.mkdir(parents=True, exist_ok=True)
        (config / "keys.env").write_text(f"{provider.upper()}_ACCESS_TOKEN=local-token\n")
        record = resolve_provider_credentials(provider)
        assert record.path == Path.home() / ".co" / "keys.env"
        assert record.get("ACCESS_TOKEN") == "local-token"


class TestTheDeployStillSetsIt:
    """The one place it belongs: the unit's environment on the server, where it
    describes the machine it is on rather than the one that made the file."""

    def test_the_deploy_rewrites_it_for_the_server(self):
        from connectonion.cli.commands import deploy_to_server as dts

        out = dts._env_for_server({"AGENT_CONFIG_PATH": "/Users/someone/.co"}, "my-agent")

        assert out["AGENT_CONFIG_PATH"] == f"{dts.SRV}/my-agent/.co"

    def test_a_project_without_it_needs_no_rewriting(self):
        from connectonion.cli.commands import deploy_to_server as dts

        out = dts._env_for_server({"OPENONION_API_KEY": "k"}, "my-agent")

        assert "AGENT_CONFIG_PATH" not in out
