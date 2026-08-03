"""The deploy step whose whole job is preventing a permission failure.

`_sync_code` chowns the deployed tree to the user the service runs as, and the
comment above it says exactly why:

    An agent that ran as root before left root-owned logs and state behind, and
    the first thing the unprivileged process does is fail to write its own log —
    PermissionError: [Errno 13] Permission denied: '.co/logs/oo.log'

Then it discarded whether the chown worked:

    _ssh(target, f"sudo chown -R {user}: {SRV}/{agent}", timeout=120)

If sudo is not passwordless on that box, or the chown fails for any other
reason, the deploy prints success and the agent breaks on its first write. Since
#585 it also breaks on its first *read* of a trust list, with "cannot read
.co/blocklist.txt" — a runtime error whose cause was a deploy that said it was
fine.

A step that exists to prevent a specific failure has to say when it did not.
"""

import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr="sudo: a password is required"):
    return subprocess.CompletedProcess(args=[], returncode=1, stdout="", stderr=stderr)


@pytest.fixture
def project(tmp_path):
    (tmp_path / 'agent.py').write_text("# agent\n")
    return tmp_path


class TestAFailedChownFailsTheDeploy:

    def test_it_does_not_report_success(self, project, capsys):
        with patch.object(dts.subprocess, 'run', return_value=_ok()), \
             patch.object(dts, '_ssh', return_value=_fail()), \
             patch.object(dts, '_remote_user', return_value='co'):
            ok = dts._sync_code('host', 'ledger', project)

        assert ok is False, (
            "the tree may still be root-owned and the deploy said it was fine"
        )

    def test_it_says_what_is_wrong(self, project, capsys):
        with patch.object(dts.subprocess, 'run', return_value=_ok()), \
             patch.object(dts, '_ssh', return_value=_fail()), \
             patch.object(dts, '_remote_user', return_value='co'):
            dts._sync_code('host', 'ledger', project)

        out = capsys.readouterr().out
        assert 'chown' in out.lower() or 'owner' in out.lower(), out
        assert 'sudo' in out, "the reason sudo gave is the actionable part"


class TestNothingElseChanges:

    def test_a_working_deploy_still_succeeds(self, project):
        with patch.object(dts.subprocess, 'run', return_value=_ok()), \
             patch.object(dts, '_ssh', return_value=_ok()), \
             patch.object(dts, '_remote_user', return_value='co'):
            assert dts._sync_code('host', 'ledger', project) is True

    def test_a_failed_rsync_still_fails_first(self, project, capsys):
        """rsync failing means there is nothing to chown; that message wins."""
        with patch.object(dts.subprocess, 'run', return_value=_fail("rsync: boom")), \
             patch.object(dts, '_ssh', return_value=_ok()), \
             patch.object(dts, '_remote_user', return_value='co'):
            assert dts._sync_code('host', 'ledger', project) is False

        assert 'rsync' in capsys.readouterr().out.lower()


class TestTheRecordedPortIsWrittenOrMentioned:
    """`.co/port` is how the next deploy knows which port this agent kept.

    The write was unchecked. When it fails, `_port_for` finds nothing recorded
    on the next deploy, probes for a free port — and the old one is now held by
    the running agent, so it picks a different one. Caddy is rewritten to
    follow, so this is not an outage; it is a port that climbs by one every
    deploy while the operator reads "8000 is taken on this machine" with no
    cause they can find.

    Not worth failing a deploy over. Worth one line.
    """

    def test_a_failed_write_is_mentioned(self, capsys):
        from unittest.mock import patch

        with patch.object(dts, '_ssh', return_value=_fail("Read-only file system")):
            dts._record_port('host', 'ledger', 8003)

        out = capsys.readouterr().out
        assert 'port' in out.lower()
        assert '8003' in out

    def test_a_successful_write_says_nothing(self, capsys):
        from unittest.mock import patch

        with patch.object(dts, '_ssh', return_value=_ok()):
            dts._record_port('host', 'ledger', 8003)

        assert capsys.readouterr().out == ""
