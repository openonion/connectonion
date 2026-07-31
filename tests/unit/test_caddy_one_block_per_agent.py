"""The Caddyfile holds one block per agent, and a hostname keeps its owner.

It used to hold exactly one block and be replaced wholesale, so deploying a
second agent to a machine silently took the first one's hostname: the first
agent kept running, on its own port, unreachable by the name it had been
published under, with nothing said about it. openonion/connectonion#309
"""

import subprocess
from unittest.mock import patch

import pytest

from connectonion.cli.commands import deploy_to_server as dts


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


class TestOneBlockPerAgent:
    def test_a_second_agent_does_not_erase_the_first(self):
        first = dts._caddyfile_with("", "alpha", "a.example.com", 8000)

        both = dts._caddyfile_with(first, "beta", "b.example.com", 8001)

        assert "alpha" in both and "8000" in both
        assert "beta" in both and "8001" in both

    def test_redeploying_replaces_that_agents_block_only(self):
        both = dts._caddyfile_with(
            dts._caddyfile_with("", "alpha", "a.example.com", 8000),
            "beta", "b.example.com", 8001)

        again = dts._caddyfile_with(both, "beta", "b.example.com", 8099)

        assert again.count("connectonion:beta") == 1, "duplicated its own block"
        assert "8099" in again and "8001" not in again
        assert "8000" in again, "the other agent's block was disturbed"

    def test_a_block_is_keyed_by_agent_not_by_hostname(self):
        """A hostname that changed hands would otherwise leave two blocks
        claiming it, and Caddy serving whichever it read last."""
        one = dts._caddyfile_with("", "alpha", "a.example.com", 8000)

        moved = dts._caddyfile_with(one, "alpha", "moved.example.com", 8000)

        assert moved.count("connectonion:alpha") == 1
        assert "a.example.com" not in moved

    def test_an_unrelated_handwritten_block_survives(self):
        """The operator's own Caddy config is not ours to delete."""
        handwritten = "example.org {\n\trespond \"hi\"\n}\n"

        result = dts._caddyfile_with(handwritten, "alpha", "a.example.com", 8000)

        assert "example.org" in result


class TestAHostnameKeepsItsOwner:
    def test_the_owner_is_reported(self):
        one = dts._caddyfile_with("", "alpha", "a.example.com", 8000)

        assert dts._caddy_owner_of(one, "a.example.com") == "alpha"
        assert dts._caddy_owner_of(one, "b.example.com") is None

    def test_a_second_agent_is_told_rather_than_taking_it(self, capsys):
        one = dts._caddyfile_with("", "alpha", "shared.example.com", 8000)
        written = []

        def fake_ssh(target, command, timeout=300):
            if command.startswith("cat /etc/caddy"):
                return _ok(one)
            written.append(command)
            return _ok("active")

        with patch.object(dts, "_ssh", side_effect=fake_ssh):
            assert dts._ensure_caddy("co@h", "beta", "shared.example.com", 8001) is True

        out = " ".join(capsys.readouterr().out.split())
        assert "already serves 'alpha'" in out
        assert "no public name of its own" in out
        assert not any("Caddyfile" in c and "cat" not in c for c in written), \
            "it rewrote the config anyway"

    def test_the_owner_can_still_redeploy_itself(self):
        one = dts._caddyfile_with("", "alpha", "shared.example.com", 8000)
        wrote = []

        def fake_ssh(target, command, timeout=300):
            if command.startswith("cat /etc/caddy"):
                return _ok(one)
            wrote.append(command)
            return _ok("active")

        with patch.object(dts, "_ssh", side_effect=fake_ssh), \
             patch.object(dts, "_caddy_running", return_value=True):
            dts._ensure_caddy("co@h", "alpha", "shared.example.com", 8000)

        assert not wrote, "an unchanged config should not be rewritten"
