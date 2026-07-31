"""A server can host more than one agent, and only the port stopped it.

Two agents defaulting to 8000 means the second dies on "address already in use"
while `Restart=always` keeps it flapping — so `systemctl is-active` answers
`active` and the deploy reports success for an agent that has never served a
request. openonion/connectonion#450
"""

import subprocess
from unittest.mock import patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class TestChoosingThePort:
    def test_a_lone_agent_still_gets_8000(self):
        """The common case must read exactly as it always did."""
        def fake_ssh(target, command, timeout=300):
            if "cat" in command:
                return _ok("")                      # nothing recorded yet
            return _ok("8000")                      # nothing listening

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            assert dts._port_for("co@h", "solo", dts.DEFAULT_PORT) == 8000

    def test_a_second_agent_gets_the_next_free_one(self):
        def fake_ssh(target, command, timeout=300):
            if "cat" in command:
                return _ok("")
            return _ok("8001")                      # 8000 held by the first agent

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            assert dts._port_for("co@h", "second", dts.DEFAULT_PORT) == 8001

    def test_a_redeploy_keeps_the_port_it_had(self):
        """The Caddyfile points at this number; a port that moved would leave
        the hostname proxying to nothing."""
        def fake_ssh(target, command, timeout=300):
            if "cat" in command:
                return _ok("8003\n")
            raise AssertionError("should not have probed — it was recorded")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            assert dts._port_for("co@h", "known", dts.DEFAULT_PORT) == 8003

    def test_a_port_the_project_asked_for_is_honoured(self):
        """An explicit port is the operator's own arrangement, not ours to move."""
        with patch.object(dts, "_ssh", side_effect=lambda *a, **k: _ok("")):
            assert dts._port_for("co@h", "explicit", 9000) == 9000

    def test_an_unreadable_probe_falls_back_rather_than_guessing(self):
        with patch.object(dts, "_ssh", side_effect=lambda *a, **k: _ok("none")):
            assert dts._port_for("co@h", "x", dts.DEFAULT_PORT) == dts.DEFAULT_PORT


class TestTheAgentIsToldWhichPort:
    def test_the_unit_carries_it(self):
        unit = dts._unit_text("a", "agent.py", user="co", port=8001)

        assert "Environment=AGENT_PORT=8001" in unit

    def test_a_default_port_needs_no_variable(self):
        """Nothing is added when there is nothing to say."""
        unit = dts._unit_text("a", "agent.py", user="co")

        assert "AGENT_PORT" not in unit


class TestHostReadsIt:
    def test_the_environment_supplies_the_default(self, monkeypatch):
        """host() must pick it up without the author's agent.py changing."""
        import inspect
        from connectonion.network.host import server

        src = inspect.getsource(server.host)
        assert "AGENT_PORT" in src
        assert src.index("AGENT_PORT") < src.index("load_host_config")

    def test_an_explicit_port_still_wins(self, monkeypatch):
        """Only the default is replaced — code and host.yaml outrank the box."""
        import inspect
        from connectonion.network.host import server

        src = inspect.getsource(server.host)
        assert "if port is None" in src
