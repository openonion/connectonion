"""A project made by `co create` can let someone in.

`co init` mints `CO_INVITE_CODE` into the project .env — one code per agent,
generated once, never regenerated (#561 replaced the shipped
`invite_code: [OpenOnion]`, which was one password for every deployment,
published in this repository).

`co create` never learned to. It is the command the docs lead with, and what it
produces starts up saying:

    Invite: no one can onboard — CO_INVITE_CODE is not set.
    Add it to .env, or run `co init` to mint one.

The advice is for a different command. `co init` works on a directory that is
already a project; running it inside a created one to obtain a code is not a
path anyone would find, and until they do, the agent is unreachable by anyone
who is not already an admin.

Observed by running the real commands: `co create smoke-agent --template co-ai`
wrote AGENT_ADDRESS, AGENT_EMAIL, IS_EMAIL_ACTIVE and OPENONION_API_KEY — and
no code.
"""

import re
from pathlib import Path

import pytest


CODE = re.compile(r"^CO_INVITE_CODE=[A-Z2-9]{5}-[A-Z2-9]{5}-[A-Z2-9]{5}$", re.M)


def _seed_global_keys() -> None:
    """conftest's autouse fixture already points HOME at a tmp dir."""
    home = Path.home()
    (home / ".co").mkdir(parents=True, exist_ok=True)
    (home / ".co" / "keys.env").write_text(
        "OPENONION_API_KEY=token\nAGENT_ADDRESS=0xabc\n"
    )


def _create(tmp_path, monkeypatch, name="admits-people") -> str:
    _seed_global_keys()
    monkeypatch.chdir(tmp_path)

    from connectonion.cli.commands.create import handle_create

    handle_create(name=name, ai=False, key=None, template="co-ai",
                  description=None, yes=True, parent_dir=tmp_path)
    return (tmp_path / name / ".env").read_text()


class TestTheCodeIsThere:

    def test_a_created_project_has_one(self, tmp_path, monkeypatch):
        env = _create(tmp_path, monkeypatch)

        assert "CO_INVITE_CODE=" in env, env

    def test_it_is_shaped_like_something_a_person_can_type(self, tmp_path, monkeypatch):
        """Three groups of five, from an alphabet with no O/0 and no I/1 — it
        gets read off a screen and typed on a phone."""
        env = _create(tmp_path, monkeypatch)

        assert CODE.search(env), env

    def test_it_appears_exactly_once(self, tmp_path, monkeypatch):
        """A duplicate in the file holding the agent's way in is how people
        stop trusting the file (#589)."""
        env = _create(tmp_path, monkeypatch)

        assert env.count("CO_INVITE_CODE=") == 1, env


class TestTwoProjectsAreTwoDoors:

    def test_each_project_gets_its_own(self, tmp_path, monkeypatch):
        """One code for every deployment is what #561 removed. A second
        project must not inherit the first one's."""
        first = _create(tmp_path, monkeypatch, name="one")
        second = _create(tmp_path, monkeypatch, name="two")

        assert CODE.search(first).group() != CODE.search(second).group()


class TestTheRestOfTheEnvIsUnharmed:

    def test_the_credentials_are_still_written(self, tmp_path, monkeypatch):
        env = _create(tmp_path, monkeypatch)

        assert "OPENONION_API_KEY=" in env
        assert "AGENT_ADDRESS=" in env

    def test_no_machine_path_travels(self, tmp_path, monkeypatch):
        """#604's rule holds on this path too."""
        env = _create(tmp_path, monkeypatch)

        assert "AGENT_CONFIG_PATH" not in env
