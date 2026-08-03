"""The way in must not be a string published in this repository.

A stock `co init -t co-ai` + `co deploy` produced an agent that announced
`Invite: OpenOnion` in its own logs — the constant from
trust/policies/careful.md. Opening its public URL in a fresh browser context
and typing that word got a working session in five seconds.

`contact` is in the default allow list, so admission is a session, not a
read-only peek; and the approval prompt does not know who is asking (#551), so
the stranger is offered "Trust bash for this session" and their answer counts.
"""

import pytest

from connectonion.network.trust.fast_rules import parse_policy, evaluate_request


CAREFUL = (
    "connectonion/network/trust/policies/careful.md"
)


def policy(text):
    config, _ = parse_policy(text)
    return config


class TestTheShippedPolicies:
    def test_no_policy_ships_a_literal_invite_code(self):
        """Whatever the default is, it cannot be a value in the repository."""
        import pathlib
        for path in pathlib.Path("connectonion/network/trust/policies").glob("*.md"):
            config, _ = parse_policy(path.read_text(encoding="utf-8"))
            codes = (config.get("onboard") or {}).get("invite_code") or []
            literals = [c for c in codes if not str(c).startswith("$")]
            assert not literals, f"{path.name} ships {literals}"


class TestReadingTheCodeFromTheEnvironment:
    def test_a_placeholder_resolves_from_the_environment(self, monkeypatch):
        monkeypatch.setenv("CO_INVITE_CODE", "REAL-CODE-123")
        config = policy("---\nonboard:\n  invite_code: [$CO_INVITE_CODE]\n"
                        "default: deny\n---\n")

        assert evaluate_request(config, "0xstranger",
                                {"invite_code": "REAL-CODE-123"}) == "allow"

    def test_the_placeholder_itself_is_never_a_code(self, monkeypatch):
        """Typing the literal text of the placeholder must not work."""
        monkeypatch.setenv("CO_INVITE_CODE", "REAL-CODE-123")
        config = policy("---\nonboard:\n  invite_code: [$CO_INVITE_CODE]\n"
                        "default: deny\n---\n")

        assert evaluate_request(config, "0xstranger",
                                {"invite_code": "$CO_INVITE_CODE"}) != "allow"

    def test_an_unset_variable_closes_the_door(self, monkeypatch):
        """No code configured is not an invitation — it is a closed door.

        The alternative, falling back to a default, is exactly how a published
        constant became every agent's password.
        """
        monkeypatch.delenv("CO_INVITE_CODE", raising=False)
        config = policy("---\nonboard:\n  invite_code: [$CO_INVITE_CODE]\n"
                        "default: deny\n---\n")

        for attempt in ["", "$CO_INVITE_CODE", "OpenOnion", "anything"]:
            assert evaluate_request(config, "0xstranger",
                                    {"invite_code": attempt}) != "allow", attempt

    def test_a_literal_code_still_works(self, monkeypatch):
        """An operator who writes their own code into trust.md keeps working."""
        config = policy("---\nonboard:\n  invite_code: [B7HSW-6Y6P4]\n"
                        "default: deny\n---\n")
        assert evaluate_request(config, "0xs", {"invite_code": "B7HSW-6Y6P4"}) == "allow"
