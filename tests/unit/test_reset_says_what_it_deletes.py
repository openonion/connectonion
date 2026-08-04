"""`co reset` names what it destroys, and destroys what it names.

The warning shown before the prompt says:

    ⚠️  WARNING: This will DELETE ALL your ConnectOnion data
    You will lose:
      • Your account and balance
      • All transaction history
      • Your Ed25519 keypair
      • All configurations and credentials

The code removes two paths:

    keys_dir = global_dir / "keys";  shutil.rmtree(keys_dir)
    keys_env = global_dir / "keys.env";  keys_env.unlink()

Everything else in `~/.co` survives — on this machine that is `skills/`,
`subs/`, `backups/`, `browser_context/`, `blocklist.txt`, `agent.json`,
`address.json` and the logs.

The file describes its own blast radius three ways and only one of them is
right. The LLM-Note header says both "deletes ~/.co/keys/, ~/.co/keys.env"
(true) and "deletes entire ~/.co/ directory contents" (false), and the code
comment above the two unlinks reads `# Delete everything`.

Overstating destruction is the safe direction to be wrong in, and it is still
wrong: someone reading it cannot tell whether their skills and subscriptions
survive a reset, and they do. For a command whose whole job is to destroy
things, what it destroys is the one thing its description has to get right.

These tests pin the real blast radius rather than the wording, so the wording
cannot drift away from it again.
"""

import shutil

import pytest


@pytest.fixture
def a_home_with_things_in_it(tmp_path, monkeypatch):
    """A ~/.co holding rather more than keys."""
    from pathlib import Path

    co = tmp_path / ".co"
    (co / "keys").mkdir(parents=True)
    (co / "keys" / "agent.key").write_bytes(b"x" * 32)
    (co / "keys.env").write_text("OPENONION_API_KEY=old\n")

    # the things a real ~/.co accumulates
    (co / "skills" / "mine").mkdir(parents=True)
    (co / "skills" / "mine" / "SKILL.md").write_text("---\nname: mine\n---\n\nDo it.\n")
    (co / "subs").mkdir()
    (co / "subs" / "someone.json").write_text("{}")
    (co / "backups").mkdir()
    (co / "blocklist.txt").write_text("0xdeadbeef\n")
    (co / "agent.json").write_text('{"name": "old"}')

    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    return co


def _delete_the_way_reset_does(co):
    """The two removals from handle_reset, without the prompt or the network."""
    keys_dir = co / "keys"
    if keys_dir.exists():
        shutil.rmtree(keys_dir)
    keys_env = co / "keys.env"
    if keys_env.exists():
        keys_env.unlink()


class TestWhatIsActuallyDestroyed:

    def test_the_keypair_goes(self, a_home_with_things_in_it):
        co = a_home_with_things_in_it

        _delete_the_way_reset_does(co)

        assert not (co / "keys" / "agent.key").exists()

    def test_the_credentials_go(self, a_home_with_things_in_it):
        co = a_home_with_things_in_it

        _delete_the_way_reset_does(co)

        assert not (co / "keys.env").exists()


class TestWhatSurvives:
    """Named individually, because \"all configurations and credentials\" is what
    the warning claims and none of these are covered by it."""

    @pytest.mark.parametrize("survivor", [
        "skills/mine/SKILL.md",
        "subs/someone.json",
        "backups",
        "blocklist.txt",
        "agent.json",
    ])
    def test_it_is_still_there(self, a_home_with_things_in_it, survivor):
        co = a_home_with_things_in_it

        _delete_the_way_reset_does(co)

        assert (co / survivor).exists(), f"{survivor} was removed; the warning is right and this test is wrong"


class TestTheWarningMatchesIt:
    """The text a user reads before typing Y."""

    def _warning(self) -> str:
        import inspect

        from connectonion.cli.commands import reset_commands

        return inspect.getsource(reset_commands.handle_reset)

    def test_it_does_not_claim_everything_goes(self):
        warning = self._warning()

        assert "DELETE ALL your ConnectOnion data" not in warning, (
            "the warning says everything goes; skills, subs, backups and the "
            "blocklist survive"
        )

    def test_it_does_not_claim_all_configurations_go(self):
        assert "All configurations and credentials" not in self._warning()

    def test_it_names_the_keypair_and_the_credentials(self):
        """What it does destroy still has to be said plainly."""
        warning = self._warning().lower()

        assert "keypair" in warning
        assert "keys.env" in warning or "credential" in warning

    def test_the_header_does_not_contradict_itself(self):
        from pathlib import Path

        import connectonion.cli.commands.reset_commands as module

        source = Path(module.__file__).read_text(encoding="utf-8")
        header = source[:source.index("def handle_reset")]

        assert "entire ~/.co/ directory contents" not in header
