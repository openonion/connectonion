"""A deploy does not undo a block made on the server. #1757.

`.co/whitelist.txt` and `.co/blocklist.txt` shipped like any file the author
writes. But the running agent writes them too: an admin blocks a caller through
the HTTP/WS admin endpoint or `co trust`, and `trust/tools.block()` appends to
the server's copy. The next `co deploy --to` from a laptop sent the laptop's
copy over it. Reproduced with real rsync: the server's blocklist
`['0xold', '0xattacker_blocked_live']` became `['0xold']`, and its whitelist
`['0xpartner']` became empty. The blocked caller was back in, and nothing said so.

Now a deploy keeps the server's lists. A local copy still fills in a list the
server does not have yet, so a first deploy is not left without the author's
blocklist, and `--push-trust-lists` replaces the server's on purpose.

These run `_sync_code` itself, with rsync pointed at a local directory instead
of over ssh, so they check what ends up on the server rather than the argv.
"""

import re
import shutil
import subprocess

import pytest
from typer.testing import CliRunner

from connectonion.cli.commands import deploy_to_server as dts


pytestmark = pytest.mark.skipif(shutil.which("rsync") is None, reason="needs rsync on PATH")


def _ok():
    return subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")


@pytest.fixture
def machines(tmp_path, monkeypatch):
    local, server = tmp_path / "laptop", tmp_path / "server"
    (local / ".co").mkdir(parents=True)
    (server / ".co").mkdir(parents=True)
    (local / "agent.py").write_text("print('hi')\n")

    real_run = subprocess.run

    def local_rsync(argv, **kwargs):
        # The same rsync, delivered to a directory: drop the ssh transport and
        # point the host:path destination at the fake server.
        if argv[0] != "rsync":
            return real_run(argv, **kwargs)
        argv = list(argv)
        i = argv.index("-e")
        del argv[i:i + 2]
        argv[-1] = f"{server}/"
        return real_run(argv, **kwargs)

    monkeypatch.setattr(dts.subprocess, "run", local_rsync)
    monkeypatch.setattr(dts, "_ssh", lambda *a, **k: _ok())
    monkeypatch.setattr(dts, "_remote_user", lambda target: "co")
    return local, server


def lines(path):
    return path.read_text().split()


def test_a_block_made_on_the_server_survives_a_deploy(machines):
    local, server = machines
    (local / ".co" / "blocklist.txt").write_text("0xold\n")
    (local / ".co" / "whitelist.txt").write_text("")
    (server / ".co" / "blocklist.txt").write_text("0xold\n0xattacker_blocked_live\n")
    (server / ".co" / "whitelist.txt").write_text("0xpartner\n")

    assert dts._sync_code("host", "myagent", local) is True

    assert lines(server / ".co" / "blocklist.txt") == ["0xold", "0xattacker_blocked_live"], (
        "the deploy unblocked a caller an admin blocked on the server")
    assert lines(server / ".co" / "whitelist.txt") == ["0xpartner"]


def test_a_first_deploy_still_carries_the_authors_lists(machines):
    """Keeping the server's copy must not mean a new server has none: an empty
    blocklist is the permissive direction."""
    local, server = machines
    (local / ".co" / "blocklist.txt").write_text("0xspammer\n")
    (local / ".co" / "whitelist.txt").write_text("0xpartner\n")

    assert dts._sync_code("host", "myagent", local) is True

    assert lines(server / ".co" / "blocklist.txt") == ["0xspammer"]
    assert lines(server / ".co" / "whitelist.txt") == ["0xpartner"]


def test_it_says_the_local_lists_were_not_sent(machines, capsys):
    """An author who edited a list and deployed must learn it did not land."""
    local, server = machines
    (local / ".co" / "blocklist.txt").write_text("0xnew\n")
    (server / ".co" / "blocklist.txt").write_text("0xlive\n")

    dts._sync_code("host", "myagent", local)

    out = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out)
    assert "blocklist.txt" in out and "--push-trust-lists" in out, out


def test_push_trust_lists_replaces_the_servers(machines):
    """The way to ship an intended change, including a removal."""
    local, server = machines
    (local / ".co" / "blocklist.txt").write_text("0xold\n")
    (server / ".co" / "blocklist.txt").write_text("0xold\n0xforgiven\n")

    assert dts._sync_code("host", "myagent", local, push_trust_lists=True) is True

    assert lines(server / ".co" / "blocklist.txt") == ["0xold"]


def test_code_still_syncs_with_delete(machines):
    local, server = machines
    (server / "stale.py").write_text("old\n")
    (local / ".co" / "blocklist.txt").write_text("0xold\n")

    dts._sync_code("host", "myagent", local)

    assert (server / "agent.py").exists()
    assert not (server / "stale.py").exists()


def test_the_flag_needs_to():
    from connectonion.cli.main import app

    result = CliRunner().invoke(app, ["deploy", "--push-trust-lists"])

    assert result.exit_code == 2
    assert "--to" in re.sub(r"\x1b\[[0-9;]*m", "", result.output)
