"""What `keys.env` says the address is, and what the key says it is.

`AGENT_ADDRESS` in `~/.co/keys.env` is written once, at first setup, and never
reconciled. `ensure_global_config()` has the reconcile — it rewrites the line
from the keypair — but only inside the branch that regenerates a *missing* key.
An existing key that has *changed* returns at the top:

    if key_file.exists():
        return

So after a `co reset`, or a restore from a different recovery phrase, the file
keeps naming the old identity. Reproduced from a clean HOME:

    keypair  0x8a6c70b01453      stated  0x8a6c70b01453     fresh: agree
    keypair  0x2cc36d08f71a      stated  0x8a6c70b01453     after the key changed

Every project made afterwards copies that line into its `.env`, and every deploy
ships it to a server. Observed in three places on this operator's machines:

    ~/.co/keys.env         token bills 0x10e6…   AGENT_ADDRESS 0x5616…
    /etc/…/dash-e2e.env    token bills 0x10e6…   AGENT_ADDRESS 0x5616…
    /etc/…/naturewill.env  token bills 0x5616…   AGENT_ADDRESS 0x5616…

An address is what other agents whitelist, what goes in `admins.txt`, and what
someone pastes to a colleague. Publishing one whose private key you do not hold
is worse than publishing none: everything downstream trusts a name nobody can
answer to.

The keypair is the source of truth. The line in keys.env is a copy of it, so it
is written every time rather than once — the same self-healing rule `co deploy`
already applies to `authorized_keys` and `admins.txt`.
"""

from pathlib import Path

import pytest

from connectonion import address
from connectonion.cli.commands.project_cmd_lib import ensure_global_config


def _stated() -> str:
    keys_env = Path.home() / ".co" / "keys.env"
    for line in keys_env.read_text(encoding="utf-8").splitlines():
        if line.startswith("AGENT_ADDRESS="):
            return line.split("=", 1)[1].strip()
    return ""


def _keypair() -> str:
    return address.load(Path.home() / ".co")["address"]


class TestAFreshMachine:

    def test_they_agree(self):
        ensure_global_config()

        assert _stated() == _keypair()


class TestAfterTheKeyChanges:
    """What `co reset` does, and what restoring a different phrase does."""

    def test_the_stated_address_follows(self):
        ensure_global_config()
        before = _keypair()

        address.save(address.generate(), Path.home() / ".co")
        ensure_global_config()

        assert _keypair() != before, "the fixture did not change the key"
        assert _stated() == _keypair(), (
            f"keys.env still names {_stated()[:14]} while the key is "
            f"{_keypair()[:14]} — every project made from here inherits it"
        )


class TestNothingElseIsDisturbed:

    def test_the_other_lines_survive(self):
        ensure_global_config()
        keys_env = Path.home() / ".co" / "keys.env"
        keys_env.write_text(keys_env.read_text() + "OPENONION_API_KEY=token\n"
                            "GEMINI_API_KEY=key\n", encoding="utf-8")

        address.save(address.generate(), Path.home() / ".co")
        ensure_global_config()

        text = keys_env.read_text()
        assert "OPENONION_API_KEY=token" in text
        assert "GEMINI_API_KEY=key" in text

    def test_the_address_is_not_written_twice(self):
        ensure_global_config()
        address.save(address.generate(), Path.home() / ".co")
        ensure_global_config()

        keys_env = Path.home() / ".co" / "keys.env"
        lines = [l for l in keys_env.read_text().splitlines()
                 if l.startswith("AGENT_ADDRESS=")]

        assert len(lines) == 1, lines

    def test_an_unchanged_key_leaves_the_file_alone(self):
        """The common case is a no-op, and must stay one."""
        ensure_global_config()
        keys_env = Path.home() / ".co" / "keys.env"
        before = keys_env.read_text()

        ensure_global_config()

        assert keys_env.read_text() == before
