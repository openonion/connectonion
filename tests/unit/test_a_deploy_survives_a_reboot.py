"""A deploy that reports success leaves the agent set to start at boot.

`systemctl enable` lives inside `_write_unit_if_changed()`, after the early
return that skips the write when the unit text is unchanged:

    current = _ssh(target, f"cat {unit_path} …")
    if current.returncode == 0 and current.stdout == wanted:
        return True                    # ← enable never runs

The unit text is unchanged on every deploy after the first. So enablement is
decided once, by whatever the first deploy happened to do, and never revisited.
Observed on a real box — `naturewill: active/disabled` after a clean deploy that
printed the green success line:

    ssh <server> 'sudo systemctl disable naturewill'
    co deploy --to <server>          # ✓ naturewill is running on <server>
    ssh <server> 'systemctl is-enabled naturewill'
    disabled

The machine reboots, the agent does not come back, and nothing said so. That is
the worst shape a failure can take: it is invisible until an unrelated event —
a kernel update, a power cut — turns it into an outage nobody connects to a
deploy weeks earlier. #574.

`systemctl enable` is idempotent and costs one ssh round trip, so it belongs on
the deploy path unconditionally, not inside a branch about file contents.
"""

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts


def run(stdout="", returncode=0):
    return SimpleNamespace(stdout=stdout, stderr="", returncode=returncode)


def commands_for(unit_on_server: str):
    """Run the unit step against a fake server; return every command it sent."""
    sent = []

    def fake_ssh(tgt, command, timeout=None, **kwargs):
        sent.append(command)
        if command.strip() == "id -un":
            return run("deployer\n")
        if command.startswith("cat /etc/systemd/system/"):
            if unit_on_server is None:
                return run("", returncode=1)
            return run(unit_on_server)
        return run()

    with patch.object(dts, "_ssh", side_effect=fake_ssh):
        dts._write_unit_if_changed("nw-e2e", "billing", "agent.py")

    return sent


def _wanted_unit() -> str:
    return dts._unit_text("billing", "agent.py", None, user="deployer", port=None)


class TestTheUnitIsAlreadyThere:
    """The common case: every deploy after the first."""

    def test_it_is_still_enabled(self):
        sent = commands_for(unit_on_server=_wanted_unit())

        assert any("systemctl enable billing" in c for c in sent), sent

    def test_the_unit_is_not_rewritten_for_nothing(self):
        """The early return was there for a reason — a daemon-reload on every
        deploy hides whether a restart came from new code or a new unit."""
        sent = commands_for(unit_on_server=_wanted_unit())

        assert not any("UNITEOF" in c for c in sent), sent
        assert not any("daemon-reload" in c for c in sent), sent


class TestTheUnitIsNew:

    def test_it_is_written_and_enabled(self):
        sent = commands_for(unit_on_server=None)

        assert any("UNITEOF" in c for c in sent), sent
        assert any("systemctl enable billing" in c for c in sent), sent


class TestTheUnitChanged:

    def test_it_is_rewritten_and_enabled(self):
        sent = commands_for(unit_on_server="[Unit]\nDescription=something else\n")

        assert any("UNITEOF" in c for c in sent), sent
        assert any("systemctl enable billing" in c for c in sent), sent
