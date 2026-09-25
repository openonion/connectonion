"""The startup banner states what is configured, not what has succeeded.

Two lines assert more than the process knows at the moment they print:

    ↳ chat.openonion.ai ↗
    ✓ relay

`✓ relay` is `"✓ relay" if relay_url else "no relay"` — a green tick for
"a URL is set", printed before any connection is attempted. Against a relay
that refuses instantly it still printed the tick, and the operator reading it
has been told their agent is reachable.

`chat_url` is `f"https://chat.openonion.ai/{address}"` regardless of which
relay the agent announces on. That was accidentally true while every agent was
on the public relay; #626 made a private `relay_url` in host.yaml actually
work, so now it can point at a site that has never heard of the agent.

Neither is a lie the code could have caught: the banner prints during startup,
before the relay loop has connected to anything. So it should say what it has —
the relay it is about to use — and leave success to the lines that know:
`relay connection error …`, `relay reconnected`, and the `♥` for a terminal.
"""

import re

import pytest

from connectonion.network.host.server import DEFAULT_RELAY_URL, _print_host_banner


ADDRESS = "0x" + "a" * 64
PRIVATE = "wss://relay.example.internal/ws"


def _banner(capsys, relay_url) -> str:
    _print_host_banner(port=8000, address=ADDRESS, relay_url=relay_url,
                       trust="careful", trust_config={}, co_dir=None)
    out = capsys.readouterr()
    return out.out + out.err


class TestNoTickForSomethingUntried:

    def test_the_public_relay_gets_no_success_mark(self, capsys):
        banner = _banner(capsys, DEFAULT_RELAY_URL)

        assert "✓ relay" not in banner, banner

    def test_a_private_relay_gets_no_success_mark(self, capsys):
        banner = _banner(capsys, PRIVATE)

        assert "✓ relay" not in banner, banner


class TestItStillSaysWhichRelay:

    def test_the_public_one_is_named(self, capsys):
        banner = _banner(capsys, DEFAULT_RELAY_URL)

        assert "oo.openonion.ai" in banner

    def test_a_private_one_is_named(self, capsys):
        banner = _banner(capsys, PRIVATE)

        assert "relay.example.internal" in banner

    def test_no_relay_still_says_so(self, capsys):
        banner = _banner(capsys, None)

        assert "no relay" in banner


class TestTheChatLinkMatchesTheRelay:

    def test_it_is_shown_for_the_public_relay(self, capsys):
        """That is the site that can find an agent announced there."""
        banner = _banner(capsys, DEFAULT_RELAY_URL)

        assert "chat.openonion.ai" in banner

    def test_it_is_not_shown_for_a_private_relay(self, capsys):
        """chat.openonion.ai cannot reach an agent that never announced to it."""
        banner = _banner(capsys, PRIVATE)

        assert "chat.openonion.ai" not in banner, banner

    def test_it_is_not_shown_without_a_relay(self, capsys):
        banner = _banner(capsys, None)

        assert "chat.openonion.ai" not in banner, banner


class TestWhatTheBannerIsFor:

    def test_the_address_is_still_there(self, capsys):
        assert ADDRESS in _banner(capsys, DEFAULT_RELAY_URL)

    def test_the_local_url_is_still_there(self, capsys):
        assert "localhost:8000" in _banner(capsys, DEFAULT_RELAY_URL)


class TestAConfigFileThatIsNotThere:
    """Re-test of 1.8.8b9: in a project with no .co/host.yaml the banner still
    printed `config: <project>/.co/host.yaml`, and the port-in-use hint said
    to change `port:` in it -- a file to edit that did not exist."""

    @staticmethod
    def _flat(text):
        return " ".join(re.sub(r"\x1b\[[0-9;]*m", "", text).split())

    def _banner_in(self, capsys, co_dir):
        _print_host_banner(port=8000, address=ADDRESS, relay_url=None,
                           trust="careful", trust_config={}, co_dir=co_dir)
        return self._flat(capsys.readouterr().out)

    def test_the_banner_says_there_is_none(self, capsys, tmp_path):
        banner = self._banner_in(capsys, tmp_path / ".co")

        assert "config: none (defaults)" in banner, banner
        assert f"create {(tmp_path / '.co' / 'host.yaml').resolve()} to change them" in banner

    def test_the_paths_are_not_broken_on_a_narrow_console(self, capsys, tmp_path, monkeypatch):
        """CI's log is 80 columns and forces colour; the path must stay whole
        there too, since it is printed to be copied."""
        monkeypatch.setenv("COLUMNS", "40")
        monkeypatch.setenv("FORCE_COLOR", "1")
        deep = tmp_path / ("a-rather-long-project-directory-name" * 2)
        deep.mkdir()
        _print_host_banner(port=8000, address=ADDRESS, relay_url=None,
                           trust="careful", trust_config={}, co_dir=deep / ".co")
        lines = re.sub(r"\x1b\[[0-9;]*m", "", capsys.readouterr().out).splitlines()

        assert any(str((deep / ".co" / "host.yaml").resolve()) in line for line in lines), lines
        assert any(str((deep / ".co" / "logs").resolve()) in line for line in lines), lines

    def test_the_banner_names_one_that_exists(self, capsys, tmp_path):
        (tmp_path / ".co").mkdir()
        (tmp_path / ".co" / "host.yaml").write_text("port: 8000\n")

        banner = self._banner_in(capsys, tmp_path / ".co")

        assert "config: none" not in banner, banner
        assert f"config: {(tmp_path / '.co' / 'host.yaml').resolve()}" in banner, banner

    def test_the_port_hint_says_to_create_it(self, tmp_path):
        from connectonion.network.host.server import _port_taken_message

        hint = self._flat(_port_taken_message(8000, tmp_path / ".co"))

        assert "does not exist yet" in hint and "port: 8001" in hint
        assert "AGENT_PORT=8001" in hint

    def test_the_port_hint_says_to_change_one_that_exists(self, tmp_path):
        from connectonion.network.host.server import _port_taken_message
        (tmp_path / ".co").mkdir()
        (tmp_path / ".co" / "host.yaml").write_text("port: 8000\n")

        hint = self._flat(_port_taken_message(8000, tmp_path / ".co"))

        assert "Change `port:` in" in hint and "does not exist" not in hint
