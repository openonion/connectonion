"""A server that will not take your key is recoverable without paying again.

`_wait_until_it_accepts_your_key` returns False rather than failing the command,
which is right — the machine exists and is charged for either way. But the
operator was then left with a $360 machine, a ✓ ready banner and no route in:
`co server check` reported the same failure, and the only repair was destroy and
recreate. openonion/connectonion#449
"""

import subprocess
from unittest.mock import Mock, patch

import pytest

from connectonion.cli.commands import server_commands as sc


def _ok(stdout=""):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=stdout, stderr="")


def _fail(stderr="Permission denied (publickey)."):
    return subprocess.CompletedProcess(args=[], returncode=255, stdout="", stderr=stderr)


def _response(status, payload=None):
    return Mock(status_code=status, json=Mock(return_value=payload or {}), content=b"{}")


@pytest.fixture
def registered(tmp_path, monkeypatch):
    monkeypatch.setattr(sc, "SERVERS_FILE", tmp_path / "servers.yaml")
    sc._update(lambda s: s.update({"prod": {"ssh": "co@1.2.3.4", "last_check": None}}))


class TestTheWaitPointsAtSomethingThatCanFixIt:
    def test_the_timeout_names_the_repair(self, capsys):
        with patch.object(sc, "_ssh", return_value=_fail()), \
             patch.object(sc, "KEY_INSTALL_TIMEOUT_SECONDS", 0):
            sc._wait_until_it_accepts_your_key("co@1.2.3.4", "prod")

        out = " ".join(capsys.readouterr().out.split())
        assert "co server fix-key prod" in out, \
            "told the operator to wait, with nothing that could change the outcome"
        assert "charged for" in out


class TestFixKey:
    def test_it_reinstalls_and_confirms(self, registered, capsys):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key",
                   return_value="k"), \
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch("requests.post", return_value=_response(200, {"name": "prod"})) as post, \
             patch.object(sc, "_forget_host_key"), \
             patch.object(sc, "_wait_until_it_accepts_your_key", return_value=True):
            assert sc.handle_server_fix_key("prod") is True

        assert post.call_args.kwargs["json"]["ssh_public_key"] == "ssh-ed25519 AAAA x"
        assert "/servers/prod/key" in post.call_args.args[0]
        assert "accepts your key" in capsys.readouterr().out

    def test_the_stale_host_key_is_dropped_first(self, registered):
        """The address may have been handed back by the provider; a key that
        changed is refused before authentication is even attempted."""
        forgotten = []

        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key",
                   return_value="k"), \
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch("requests.post", return_value=_response(200)), \
             patch.object(sc, "_forget_host_key", side_effect=forgotten.append), \
             patch.object(sc, "_wait_until_it_accepts_your_key", return_value=True):
            sc.handle_server_fix_key("prod")

        assert forgotten == ["co@1.2.3.4"]

    def test_an_unknown_server_is_refused_before_anything_is_sent(self, registered):
        with patch("requests.post") as post:
            assert sc.handle_server_fix_key("nope") is False
        post.assert_not_called()

    def test_a_machine_that_still_refuses_says_it_is_charged_for(self, registered, capsys):
        with patch("connectonion.cli.commands.project_cmd_lib.load_api_key",
                   return_value="k"), \
             patch.object(sc, "_ensure_ssh_key", return_value="ssh-ed25519 AAAA x"), \
             patch("requests.post", return_value=_response(200)), \
             patch.object(sc, "_forget_host_key"), \
             patch.object(sc, "_wait_until_it_accepts_your_key", return_value=False):
            assert sc.handle_server_fix_key("prod") is False

        assert "charged for either way" in " ".join(capsys.readouterr().out.split())
