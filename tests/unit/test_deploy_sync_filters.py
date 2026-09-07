"""What a deploy actually leaves on the server.

The existing tests in test_deploy_to_server.py assert the shape of the rsync
argv. That is how `.co/host.yaml` and `.co/OO.md` went missing for a release
without anyone noticing: the argv was exactly as asserted, and the outcome was
still wrong. These tests run the real rsync against two directories and look at
the files, so they answer the only question that matters — after a deploy, what
is on the server?
"""

import shutil
import subprocess

import pytest

from connectonion.cli.commands.deploy_to_server import RSYNC_FILTERS, _rsync_filters


pytestmark = pytest.mark.skipif(
    shutil.which("rsync") is None, reason="needs rsync on PATH"
)


@pytest.fixture
def synced(tmp_path):
    """Run the real filters over a project that has every kind of file.

    Returns the server directory, after one deploy.
    """
    local, server = tmp_path / "local", tmp_path / "server"

    # What the author writes.
    (local / ".co" / "skills" / "billing").mkdir(parents=True)
    (local / ".co" / "commands").mkdir()
    (local / ".co" / "host.yaml").write_text("name: myagent\n")
    (local / ".co" / "OO.md").write_text("call the billing skill first\n")
    (local / ".co" / "commands" / "report.md").write_text("# report\n")
    (local / ".co" / "skills" / "billing" / "SKILL.md").write_text("# billing\n")
    (local / "agent.py").write_text("print('hi')\n")

    # What the server owns and the author must never overwrite.
    (server / ".co" / "keys").mkdir(parents=True)
    (server / ".co" / "logs").mkdir()
    (server / ".co" / "keys" / "agent.key").write_text("SERVER IDENTITY")
    (server / ".co" / "logs" / "run.log").write_text("history\n")
    (server / ".co" / "admins.txt").write_text("0xdeadbeef\n")
    (server / ".co" / "provision.json").write_text("{}\n")
    # Code the author deleted locally, which should go away.
    (server / "stale.py").write_text("old\n")

    subprocess.run(
        ["rsync", "-a", "--delete", *RSYNC_FILTERS, f"{local}/", f"{server}/"],
        check=True, capture_output=True,
    )
    return server


@pytest.mark.parametrize("relpath", [
    ".co/host.yaml",
    ".co/OO.md",
    ".co/commands/report.md",
    ".co/skills/billing/SKILL.md",
    "agent.py",
])
def test_what_the_author_wrote_arrives(synced, relpath):
    """Config is what makes the agent this agent. Dropping it silently ships a
    different agent than the one that was tested."""
    assert (synced / relpath).exists(), f"{relpath} never reached the server"


def test_the_agent_keeps_its_identity(synced):
    """The reason `.co/` was excluded in the first place (#306). Overwriting this
    reissues the address and voids every trust relationship keyed to it."""
    assert (synced / ".co" / "keys" / "agent.key").read_text() == "SERVER IDENTITY"


@pytest.mark.parametrize("relpath", [
    ".co/logs/run.log",     # history a dashboard shows
    ".co/admins.txt",       # who may command the agent
    ".co/provision.json",   # convergence marker
])
def test_server_owned_state_survives_the_delete(synced, relpath):
    """`--delete` removes whatever the source lacks. Everything here exists only
    on the server, so without protection each deploy would wipe it."""
    assert (synced / relpath).exists(), f"{relpath} was deleted by the sync"


def test_deleted_code_still_goes_away(synced):
    """The protection must not turn `--delete` off for the rest of the tree."""
    assert not (synced / "stale.py").exists()


def test_gitignored_runtime_state_is_neither_replaced_nor_deleted(tmp_path):
    """The project names its state once; a deploy must leave the live copy alone."""
    local, server = tmp_path / "local", tmp_path / "server"
    local.mkdir()
    (local / ".gitignore").write_text("work/\n")
    (local / "work").mkdir()
    (local / "work" / "cache.json").write_text("STALE LAPTOP COPY")
    (local / "agent.py").write_text("print('new code')\n")

    (server / "work").mkdir(parents=True)
    (server / "work" / "cache.json").write_text("LIVE SERVER STATE")
    (server / "work" / "sentinel.json").write_text("SERVER ONLY")
    (server / "stale.py").write_text("deleted source")

    subprocess.run(
        ["rsync", "-a", "--delete", *_rsync_filters(local),
         f"{local}/", f"{server}/"],
        check=True, capture_output=True,
    )

    assert (server / "work" / "cache.json").read_text() == "LIVE SERVER STATE"
    assert (server / "work" / "sentinel.json").read_text() == "SERVER ONLY"
    assert not (server / "stale.py").exists(), "non-ignored deleted code lingered"


@pytest.mark.parametrize("relpath, server_value", [
    (".co/address.json", '{"address": "0xSERVER"}'),   # decides super-admin
    (".co/admins.txt", "0xSERVER\n"),                  # decides who may command
    (".co/provision.json", '{"schema": 3}'),
    (".co/requirements.sha256", "server-digest"),
])
def test_a_local_copy_cannot_overwrite_what_the_server_owns(
        tmp_path, relpath, server_value):
    """Protection stops `--delete`; it does not stop a *transfer*. These four
    are generated on the server or written there over ssh, so a stale local
    copy — `add_admin()` writes `.co/admins.txt` in the cwd when run locally —
    would silently change who is in charge of the deployed agent.
    """
    local, server = tmp_path / "local", tmp_path / "server"
    (local / ".co").mkdir(parents=True)
    (server / ".co").mkdir(parents=True)
    (local / relpath).write_text("LOCAL")
    (server / relpath).write_text(server_value)

    subprocess.run(
        ["rsync", "-a", "--delete", *RSYNC_FILTERS, f"{local}/", f"{server}/"],
        check=True, capture_output=True,
    )

    assert (server / relpath).read_text() == server_value


def test_a_local_key_cannot_take_over_the_server(tmp_path):
    """A project that has ever run `host()` locally has its own `.co/keys/`.
    That key must not be able to replace the server's identity."""
    local, server = tmp_path / "local", tmp_path / "server"
    (local / ".co" / "keys").mkdir(parents=True)
    (server / ".co" / "keys").mkdir(parents=True)
    (local / ".co" / "keys" / "agent.key").write_text("LOCAL")
    (server / ".co" / "keys" / "agent.key").write_text("SERVER")

    subprocess.run(
        ["rsync", "-a", "--delete", *RSYNC_FILTERS, f"{local}/", f"{server}/"],
        check=True, capture_output=True,
    )

    assert (server / ".co" / "keys" / "agent.key").read_text() == "SERVER"
