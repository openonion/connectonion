"""A trust decision has to be readable afterwards.

The operator's whole diagnostic surface for "why can't my client talk to my agent"
is this log. Today it records the denials and stays silent on the allows, so a log
that did not grow is ambiguous between *allowed* and *never asked* — the two states
that most need telling apart. It also truncates the one string the operator has to
copy into admins.txt, and prints the invite codes on every request.
"""

import logging

import pytest

from connectonion.network.trust import fast_rules


FULL_ID = "0xb2df62c9094c42eb5413731304b867e7c4a1762edcd6b3f572c1111e071bdc01"
CODE = "B7HSW-6Y6P4-BZC5Z"


@pytest.fixture
def log(caplog):
    caplog.set_level(logging.DEBUG, logger="connectonion.trust.fast_rules")
    return caplog


def decisions(log):
    """The lines that state an outcome.

    The opening line echoes the whole config, which contains the words "allow",
    "whitelisted" and "contact" whatever happens. Matching against it would let
    these tests pass on a build that decides silently, which is the bug.
    """
    return [r.message for r in log.records if "Evaluating" not in r.message]


def _config(default="deny"):
    return {
        "allow": ["admin", "whitelisted", "contact"],
        "deny": ["blocked"],
        "onboard": {"invite_code": [CODE]},
        "default": default,
    }


def test_an_allow_says_which_condition_matched(log, monkeypatch):
    monkeypatch.setattr(fast_rules, "is_blocked", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_admin", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_whitelisted", lambda _: True)
    monkeypatch.setattr(fast_rules, "is_contact", lambda _: False)

    assert fast_rules.evaluate_request(_config(), FULL_ID, {}) == "allow"

    assert any(
        "allow" in m and "whitelisted" in m for m in decisions(log)
    ), "no line says the client was allowed, and by which condition"


def test_onboarding_by_invite_code_is_recorded(log, monkeypatch):
    monkeypatch.setattr(fast_rules, "is_blocked", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_admin", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_whitelisted", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_contact", lambda _: False)
    monkeypatch.setattr(fast_rules, "promote_to_contact", lambda _: None)

    result = fast_rules.evaluate_request(_config(), FULL_ID, {"invite_code": CODE})

    assert result == "allow"
    assert any(
        "allow" in m and "invite" in m.lower() for m in decisions(log)
    ), "a stranger was promoted to contact and no line says why"


def test_the_client_id_is_logged_whole(log, monkeypatch):
    monkeypatch.setattr(fast_rules, "is_blocked", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_admin", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_whitelisted", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_contact", lambda _: False)

    fast_rules.evaluate_request(_config(), FULL_ID, {})

    assert FULL_ID in log.text, (
        "the operator's next step is to paste this id into admins.txt, "
        "and the log gives them a prefix"
    )


def test_invite_codes_are_not_written_to_the_log(log, monkeypatch):
    monkeypatch.setattr(fast_rules, "is_blocked", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_admin", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_whitelisted", lambda _: False)
    monkeypatch.setattr(fast_rules, "is_contact", lambda _: False)

    fast_rules.evaluate_request(_config(), FULL_ID, {})

    assert CODE not in log.text, "every request prints the agent's invite codes"
