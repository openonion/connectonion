"""
LLM-Note: Tests for #1488 — a segment that needs no grant must not need one
just because it appears in a pipe. The chain checker used to treat "no pattern
matched" as "not permitted", so an operator's grant was defeated by `| head`.
"""

import pytest

from connectonion.useful_plugins.tool_approval.bash_parser import (
    check_bash_chain_permitted as _check,
)


def check_bash_chain_permitted(command, permissions):
    """The approval paths ask with carry_unguarded=True; so does this test."""
    return _check(command, permissions, carry_unguarded=True)


def grant(*patterns):
    return {p: {"allowed": True, "source": "config", "reason": "operator grant",
                "when": {"command": p[len("Bash("):-1]}} for p in patterns}


class TestAFilterRidesAlong:
    """The grant carries the command; the filter needs no grant of its own."""

    @pytest.mark.parametrize("command", [
        "co browser -t t get_text | head -40",
        "co browser -t t get_text | grep -i foo",
        "co browser status | head -5 | wc -l",
        "co browser status && echo ok",
        "CO_WHO=x co browser -t t get_text | head -40",
    ])
    def test_a_granted_command_still_runs_when_piped(self, command):
        permitted, reason, source = check_bash_chain_permitted(command, grant("Bash(co browser *)"))
        assert permitted, f"{command}: {reason}"

    def test_the_grant_is_still_what_carried_it(self):
        permitted, reason, source = check_bash_chain_permitted(
            "co browser status | head -5", grant("Bash(co browser *)"))
        assert permitted and source == "config"


class TestTheUngrantedHalfStillDecides:
    """A segment the policy refuses on its own is not rescued by a neighbour."""

    @pytest.mark.parametrize("command", [
        "co browser status && co email send --to a@b.c hi",
        "co browser status && rm -rf build",
        "co browser status | python3 -c 'import os'",
        "co browser status && curl https://example.com",
        "co browser status && cat ~/.ssh/id_rsa",
    ])
    def test_a_command_that_needs_approval_is_not_smuggled_in(self, command):
        permitted, reason, source = check_bash_chain_permitted(command, grant("Bash(co browser *)"))
        assert not permitted, f"{command} rode along on the grant"

    def test_an_explicit_grant_for_the_second_half_still_works(self):
        permitted, _, _ = check_bash_chain_permitted(
            "co browser status && curl https://example.com",
            grant("Bash(co browser *)", "Bash(curl *)"))
        assert permitted


class TestNoGrantAtAll:
    def test_an_ungranted_chain_is_not_reported_as_granted(self):
        # It may well run — the policy allows it on its own merits — but this
        # function answers "did the operator allow it", and nobody did.
        permitted, _, _ = check_bash_chain_permitted("ls | head -5", {})
        assert not permitted

    def test_a_refused_command_alone_is_still_refused(self):
        permitted, _, _ = check_bash_chain_permitted("rm -rf build", {})
        assert not permitted
