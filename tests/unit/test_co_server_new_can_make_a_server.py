"""`co server new` cannot create a server, and `co server fix-key` cannot fix one.

Measured, trying to provision a machine for this release's end-to-end test:

    $ co server new rel160-e2e --yes
    No SSH key to install.
    The key is derived from your recovery phrase; without it the server would be
    created with no way in.
    co keys --ssh to check.

The recovery phrase is right there — `co keys --ssh` lists a derived key for
every registered server. The key is not missing; it is never asked for:

    def _ensure_ssh_key(name: str = None) -> Optional[str]:
        ...
        if not name:
            return None

    handle_server_fix_key:  ssh_public_line = _ensure_ssh_key()      # line 782
    handle_server_new:      ssh_public_line = _ensure_ssh_key()      # line 840

Both functions take `name` and neither passes it, so both always take the
failure branch. #464 gave `_ensure_ssh_key` the parameter when the key became
per-server (#427); the third call site was updated and these two were not.

`co server fix-key` is the worse of the two: it exists to recover a machine
that will not take your key, so the recovery path was dead as well.

Nothing caught it because the tests for these commands mock `_ensure_ssh_key`
itself — a fake that answers regardless of its arguments cannot notice that
the caller passes none.
"""

import inspect

import pytest

from connectonion.cli.commands import server_commands


class TestTheCallersAskForAKeyByName:
    """Read from the source, because the bug is the call site and a mocked
    `_ensure_ssh_key` answers happily either way."""

    @pytest.mark.parametrize("function", ["handle_server_new", "handle_server_fix_key"])
    def test_it_passes_the_server_name(self, function):
        source = inspect.getsource(getattr(server_commands, function))

        assert "_ensure_ssh_key()" not in source, (
            f"{function} calls _ensure_ssh_key with no name, which always "
            f"returns None — the command can never succeed"
        )
        assert "_ensure_ssh_key(name)" in source, source[:200]


class TestTheDerivationItself:
    """Given a name, a key really is produced."""

    def test_a_name_yields_a_public_line(self, tmp_path, monkeypatch):
        from connectonion import address
        from connectonion.cli.commands import keys_commands

        co_dir = tmp_path / ".co"
        (co_dir / "keys").mkdir(parents=True)
        identity = address.generate()
        address.save(identity, co_dir)
        (co_dir / "keys" / "recovery.txt").write_text(identity["seed_phrase"],
                                                      encoding="utf-8")
        monkeypatch.setattr(server_commands.Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.setattr(keys_commands, "_find_co_dir", lambda: co_dir)

        line = server_commands._ensure_ssh_key("rel160-e2e")

        assert line and line.startswith("ssh-ed25519 "), line

    def test_no_name_still_declines(self, tmp_path, monkeypatch):
        """Unchanged: without a name there is no per-server key to derive."""
        assert server_commands._ensure_ssh_key(None) is None

    def test_two_names_give_two_keys(self, tmp_path, monkeypatch):
        from connectonion import address
        from connectonion.cli.commands import keys_commands

        co_dir = tmp_path / ".co"
        (co_dir / "keys").mkdir(parents=True)
        identity = address.generate()
        address.save(identity, co_dir)
        (co_dir / "keys" / "recovery.txt").write_text(identity["seed_phrase"],
                                                      encoding="utf-8")
        monkeypatch.setattr(server_commands.Path, "home", classmethod(lambda cls: tmp_path))
        monkeypatch.setattr(keys_commands, "_find_co_dir", lambda: co_dir)

        assert server_commands._ensure_ssh_key("one") != server_commands._ensure_ssh_key("two")
