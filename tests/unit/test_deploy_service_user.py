"""The service runs as the user the server says we are.

`co server add --ssh` documents two target forms, `user@host` and a Host alias
from ~/.ssh/config. Deriving the account name by splitting the target on "@"
only reads the first one; an alias has no "@", so the whole alias became the
username, and systemd refused to start the unit with 217/USER — after every
stage of the deploy had reported success.
"""

from types import SimpleNamespace
from unittest.mock import patch

from connectonion.cli.commands import deploy_to_server as dts


def run(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def unit_written(target, remote_user):
    """Deploy against a fake server and return the unit text it wanted to write."""
    written = {}

    def fake_ssh(tgt, command, timeout=None, **kwargs):
        if command.strip() == "id -un":
            return run(remote_user + "\n")
        if command.startswith("cat /etc/systemd/system/"):
            return run("", returncode=1)          # no unit there yet
        if "UNITEOF" in command:                  # the heredoc carrying the unit
            written["text"] = command
        return run()

    with patch.object(dts, "_ssh", side_effect=fake_ssh):
        dts._write_unit_if_changed(target, "billing", "agent.py")

    return written.get("text", "")


def test_a_host_alias_is_not_a_username():
    text = unit_written(target="nw-e2e", remote_user="changxing")

    assert "User=changxing" in text, (
        "the unit names the ssh alias as its user; systemd exits 217/USER "
        "because no such account exists on the machine"
    )
    assert "User=nw-e2e" not in text


def test_the_user_at_host_form_still_works():
    text = unit_written(target="deploy@10.0.0.4", remote_user="deploy")

    assert "User=deploy" in text


def test_a_host_block_overriding_user_is_honoured():
    # ~/.ssh/config: Host box / User svc — the target string says nothing about
    # who we land as, and only the server can answer that.
    text = unit_written(target="box", remote_user="svc")

    assert "User=svc" in text
