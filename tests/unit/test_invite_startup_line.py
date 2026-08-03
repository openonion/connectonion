"""What the agent says about its own door on startup.

Three things it must not do: print the placeholder as if it were a code, print
the real code into the log, or stay silent when the door cannot be opened at
all.

The last one is a migration hazard this release creates. An existing deployment
on the default `careful` policy, upgraded, with no CO_INVITE_CODE in its .env,
refuses every invite code — correct direction, but the operator sees only that
nobody can get in.
"""

import pytest

from connectonion.network.host.server import _invite_line


class TestWhatItPrints:
    def test_a_configured_code_is_not_printed(self, monkeypatch):
        """The code is a password. Passwords do not go in journalctl."""
        monkeypatch.setenv("CO_INVITE_CODE", "U262R-7WA6E-LGWG4")
        line = _invite_line({"onboard": {"invite_code": ["$CO_INVITE_CODE"]}})

        assert line
        assert "U262R-7WA6E-LGWG4" not in line

    def test_the_placeholder_is_never_shown_as_a_code(self, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "U262R-7WA6E-LGWG4")
        line = _invite_line({"onboard": {"invite_code": ["$CO_INVITE_CODE"]}})

        assert "$CO_INVITE_CODE" not in line

    def test_an_unresolvable_code_says_nobody_can_get_in(self, monkeypatch):
        """The silent lockout this release would otherwise ship."""
        monkeypatch.delenv("CO_INVITE_CODE", raising=False)
        line = _invite_line({"onboard": {"invite_code": ["$CO_INVITE_CODE"]}})

        assert line
        assert "CO_INVITE_CODE" in line          # names the variable to set
        assert any(w in line.lower() for w in ("no one", "nobody", "cannot"))

    def test_a_literal_code_is_still_not_printed(self):
        """An operator's own code in trust.md is just as much a password."""
        line = _invite_line({"onboard": {"invite_code": ["B7HSW-6Y6P4-BZC5Z"]}})

        assert "B7HSW-6Y6P4-BZC5Z" not in line

    def test_it_says_where_the_code_lives(self, monkeypatch):
        """Sending someone to .env for a code that is in trust.md wastes their
        afternoon. The line names the place it actually is."""
        monkeypatch.delenv("CO_INVITE_CODE", raising=False)
        literal = _invite_line({"onboard": {"invite_code": ["B7HSW-6Y6P4"]}})
        assert ".env" not in literal
        assert "policy" in literal.lower()

        monkeypatch.setenv("CO_INVITE_CODE", "U262R-7WA6E")
        from_env = _invite_line({"onboard": {"invite_code": ["$CO_INVITE_CODE"]}})
        assert ".env" in from_env
        assert "CO_INVITE_CODE" in from_env

    def test_a_dead_declaration_beside_a_live_one_is_still_mentioned(self, monkeypatch):
        """One working code does not make an unset variable stop mattering —
        whoever was given that half of the door still cannot open it."""
        monkeypatch.delenv("NOPE", raising=False)
        line = _invite_line({"onboard": {"invite_code": ["WORKS", "$NOPE"]}})
        assert "NOPE" in line

    def test_no_onboarding_configured_says_nothing(self):
        assert _invite_line({"onboard": {}}) is None
        assert _invite_line({}) is None
