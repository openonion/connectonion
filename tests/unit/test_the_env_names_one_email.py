"""The agent's email is written once in a .env, and a comment never disagrees with it.

Found on 1.8.8b7 in a fresh `co create` project:

    #   - Email address: 0xf70e677c@mail.openonion.ai
    ...
    AGENT_EMAIL=0xf70e677cc7@mail.openonion.ai

The comment was derived locally from the address (0x + 8 hex) when ~/.co/keys.env
was first written, before `co auth` ran; AGENT_EMAIL is what the backend
assigned (0x + 10 hex). `co create` copies keys.env comments and all, so every
new project carried two addresses for one agent.
"""

import re
from pathlib import Path

EMAIL = re.compile(r"[\w.]+@mail\.openonion\.ai")


def _seed(text):
    home = Path.home()  # conftest points HOME at a tmp dir
    (home / ".co").mkdir(parents=True, exist_ok=True)
    (home / ".co" / "keys.env").write_text(text)


def test_create_does_not_copy_a_comment_that_disagrees(tmp_path, monkeypatch):
    _seed("# Your agent address (Ed25519 public key) is used for:\n"
          "#   - Email address: 0xf70e677c@mail.openonion.ai\n"
          "AGENT_ADDRESS=0xf70e677cc7d5\n"
          "OPENONION_API_KEY=token\n"
          "AGENT_EMAIL=0xf70e677cc7@mail.openonion.ai\n")
    monkeypatch.chdir(tmp_path)
    from connectonion.cli.commands.create import handle_create

    handle_create(name="mail", ai=False, key=None, template="co-ai",
                  description=None, yes=True, parent_dir=tmp_path)

    env = (tmp_path / "mail" / ".env").read_text()
    assert set(EMAIL.findall(env)) == {"0xf70e677cc7@mail.openonion.ai"}, env


def test_a_new_keys_env_does_not_guess_an_email(tmp_path):
    """Before `co auth` there is no assigned email; a guessed one is the one that goes stale."""
    from connectonion.cli.commands.project_cmd_lib import ensure_global_config

    ensure_global_config()

    keys_env = (Path.home() / ".co" / "keys.env").read_text()
    assert not EMAIL.findall(keys_env), keys_env
    assert "AGENT_EMAIL" in keys_env  # the comment still says where the email lives
