"""AGENT_CONFIG_PATH describes the machine, not the project.

#438 removed the line that wrote `AGENT_CONFIG_PATH=/Users/someone/.co` into a
new project's .env, and `co deploy` learned to rewrite it for the server. The
value came back by a route neither of those covers: `co init` copies
~/.co/keys.env into the project .env key by key, and on any machine where
something once wrote AGENT_CONFIG_PATH into keys.env it is copied along with
the rest.

The failure is the same one #438 described. A project made on one machine and
run on another — cloned, rsynced, handed to a colleague — carries an absolute
path to a home directory that does not exist there, and the agent looks for its
identity and keys inside it. Unset, the code falls back to ~/.co, which is
correct everywhere. Set to someone else's home, it is correct in exactly one
place.

`co deploy` already strips it (tests/unit/test_a_project_travels.py), which is
the same judgement: the value is not portable. It should not be written in the
first place.
"""

import os
from pathlib import Path

import pytest

from connectonion.cli.commands.env_inheritance import describes_this_machine


class TestWhatIsRefused:

    def test_the_config_path_is(self):
        assert describes_this_machine("AGENT_CONFIG_PATH")

    @pytest.mark.parametrize("key", [
        "OPENONION_API_KEY", "AGENT_ADDRESS", "AGENT_EMAIL",
        "OPENAI_API_KEY", "GEMINI_API_KEY", "CO_INVITE_CODE",
    ])
    def test_the_credentials_a_project_needs_are_not(self, key):
        assert not describes_this_machine(key)


class TestARealInitDoesNotWriteIt:
    """The unit above is the rule; this is the thing the rule protects. The
    earlier fix here passed its tests and still wrote the value, because the
    tests checked the source for a template line and the value arrived through
    keys.env instead."""

    def _seed_keys_env(self) -> Path:
        """The autouse fixture in conftest already points HOME at a tmp dir."""
        home = Path.home()
        (home / ".co").mkdir(parents=True, exist_ok=True)
        (home / ".co" / "keys.env").write_text(
            "OPENONION_API_KEY=token\n"
            "AGENT_ADDRESS=0xabc\n"
            f"AGENT_CONFIG_PATH={home / '.co'}\n"
            "GEMINI_API_KEY=key\n"
        )
        return home

    def _init_in(self, tmp_path, monkeypatch) -> str:
        self._seed_keys_env()

        project = tmp_path / "project"
        project.mkdir()
        monkeypatch.chdir(project)

        from connectonion.cli.commands.init import handle_init

        handle_init(ai=False, key=None, template="none", description=None,
                    yes=True, force=True)
        return (project / ".env").read_text()

    def test_the_env_carries_no_home_directory(self, tmp_path, monkeypatch):
        env = self._init_in(tmp_path, monkeypatch)

        assert "AGENT_CONFIG_PATH" not in env, env

    def test_the_keys_the_project_needs_are_still_there(self, tmp_path, monkeypatch):
        env = self._init_in(tmp_path, monkeypatch)

        assert "OPENONION_API_KEY=" in env
        assert "GEMINI_API_KEY=" in env

    def test_co_create_does_not_write_it_either(self, tmp_path, monkeypatch):
        """`co create` builds the .env from the same file by a different loop,
        and its comment already claimed the value was not written."""
        self._seed_keys_env()
        monkeypatch.chdir(tmp_path)

        from connectonion.cli.commands.create import handle_create

        handle_create(name="travelling-agent", ai=False, key=None,
                      template="co-ai", description=None, yes=True,
                      parent_dir=tmp_path)

        env = (tmp_path / "travelling-agent" / ".env").read_text()
        assert "AGENT_CONFIG_PATH" not in env, env
        assert "OPENONION_API_KEY=" in env


class TestTheFallbackIsTheRightOne:

    def test_unset_resolves_to_the_home_of_whoever_runs_it(self, monkeypatch):
        monkeypatch.delenv("AGENT_CONFIG_PATH", raising=False)

        resolved = Path(os.getenv("AGENT_CONFIG_PATH", os.path.expanduser("~/.co")))

        assert resolved == Path.home() / ".co"
