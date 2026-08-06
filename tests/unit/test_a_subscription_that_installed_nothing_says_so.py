"""`co sub` tells you to restart your coding agent after installing no skills.

Real output, against two live publishers:

    candidate-mapping: skipped — the publisher did not publish its body
    ✓ Subscribed to naturewill-mapping (0xcf1619cb…)
      mirrored 0 skill(s) → /Users/changxing/.co/subs/naturewill-mapping
      claude: installed 0 skill(s)
      codex: installed 0 skill(s)
      openclaw: installed 0 skill(s)
      cursor: installed 0 skill(s)

    → Restart your coding agent to load the new skills.

There are no new skills. The one on offer was withheld by its publisher — which
the line above says, and which is the correct outcome — and then the command
prints a green tick and sends the reader off to restart four tools for nothing.

The subscription itself did succeed: it is recorded, so a later sync picks up
bodies if the publisher ever publishes them. That is worth saying. "Restart your
coding agent to load the new skills" is not, when the count is zero, and neither
is a per-tool `installed 0 skill(s)` roll-call that reads like work was done.

Same family as the run summary that said `0 tokens · $0.0000` and the doctor that
said "nothing wrong" with no browser installed: a confident report of an outcome
that did not happen. This one costs the reader four restarts.
"""

import pytest

from connectonion.cli.commands import sub_commands as sub


@pytest.fixture
def synced(monkeypatch, tmp_path, capsys):
    """Run one sync with the mirroring and fan-out results under test control."""
    monkeypatch.setattr(sub, "SUBS_DIR", tmp_path / "subs", raising=False)
    monkeypatch.setattr(sub, "_read_subs", lambda: [], raising=False)
    monkeypatch.setattr(sub, "_write_subs", lambda subs: None, raising=False)
    monkeypatch.setattr(sub, "_resolve_target", lambda t: (t, "pub"), raising=False)
    monkeypatch.setattr(sub, "_fetch_profile",
                        lambda address, base: {"alias": "pub"}, raising=False)

    def _run(mirrored, install_results):
        monkeypatch.setattr(sub, "_mirror_bundle",
                            lambda *a, **k: mirrored, raising=False)
        monkeypatch.setattr(sub, "install_all",
                            lambda *a, **k: install_results, raising=False)
        sub.handle_sub_sync_one("0xabc")
        return capsys.readouterr().out

    return _run


class TestNothingInstalledIsNotAnInvitationToRestart:

    def test_it_does_not_ask_for_a_restart(self, synced):
        output = synced(0, {"claude": 0, "codex": 0})

        assert "Restart your coding agent" not in output

    def test_it_says_nothing_was_installed(self, synced):
        output = synced(0, {"claude": 0, "codex": 0})

        assert "no skill" in output.lower() or "nothing" in output.lower()

    def test_the_subscription_is_still_reported(self, synced):
        """It did succeed, and a later sync is why that matters."""
        output = synced(0, {"claude": 0, "codex": 0})

        assert "Subscribed to pub" in output

    def test_the_per_tool_roll_call_is_dropped(self, synced):
        """Four lines of `installed 0 skill(s)` read like work was done."""
        output = synced(0, {"claude": 0, "codex": 0, "cursor": 0, "openclaw": 0})

        assert "installed 0 skill" not in output


class TestARealInstallStillReportsItself:

    def test_the_restart_hint_is_kept(self, synced):
        output = synced(3, {"claude": 3, "codex": 3})

        assert "Restart your coding agent" in output

    def test_the_counts_are_shown(self, synced):
        output = synced(3, {"claude": 3, "codex": 3})

        assert "mirrored 3 skill(s)" in output
        assert "claude: installed 3 skill(s)" in output

    def test_a_partial_install_still_asks_for_a_restart(self, synced):
        """One tool got a skill; that tool needs restarting."""
        output = synced(2, {"claude": 2, "codex": 0})

        assert "Restart your coding agent" in output
        assert "claude: installed 2 skill(s)" in output


class TestNoCodingAgentDetected:
    """The existing branch: bodies mirrored, nothing to install into."""

    def test_it_says_so(self, synced):
        output = synced(3, {})

        assert "No coding agents detected" in output

    def test_it_does_not_ask_for_a_restart(self, synced):
        """Nothing was installed into anything, so there is nothing to reload."""
        output = synced(3, {})

        assert "Restart your coding agent" not in output
