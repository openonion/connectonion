"""Whose account does the token in `OPENONION_API_KEY` actually bill?

`_token_for_this_account()` exists to answer that. Its docstring names the cost
of getting it wrong — "One $180 server was bought that way" — and it works: a
local JWT decode, and a re-authentication only when the token names an account
this machine does not hold the key for.

It just never runs. `load_api_key()` returns at the top:

    if api_key := os.getenv("OPENONION_API_KEY"):
        return api_key                          # <- guard skipped

and `connectonion/__init__.py` guarantees that variable is always set, because
it calls `load_dotenv(Path.cwd() / ".env")` at import time, before any command
starts. So the guard protects only the path nothing takes.

What that costs, observed on this operator's machine on 2026-08-11:

    ~/.co/keys.env   0x10e68f6d…   the real account, $408 balance
    ~/.env           0x561605f3…   a different agent, drained to $0.001

    cd ~           && co email inbox   ->  1 email    (0x5616…)
    cd ~/project/… && co email inbox   ->  full inbox (0x10e6…)

Same command, same machine, two mailboxes — and the empty one is indistinguishable
from a quiet week. Both files carried the same `AGENT_EMAIL=aaron.xie@…`, so the
declared identity agreed everywhere; only the key differed, and the key is what
picks the mailbox. It reads as "no mail arrived", never as "you are someone else".

The rule this pins: a token that names an account whose key this machine does not
hold must not be handed to a caller, whichever source it arrived from. Reaching
the environment first is not evidence that it is ours.
"""

import base64
import json
from pathlib import Path

import pytest

from connectonion.cli.commands import project_cmd_lib
from connectonion.cli.commands.project_cmd_lib import load_api_key

THIS_MACHINE = "0x" + "10e68f6d" * 8
SOMEONE_ELSE = "0x" + "561605f3" * 8


def token_with_payload(payload_value) -> str:
    """A JWT-shaped value; its signature is not checked by the local decoder."""
    payload = base64.urlsafe_b64encode(
        json.dumps(payload_value).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


def token_for(public_key: str) -> str:
    """A JWT shaped like the server's, signature not checked by the decoder."""
    return token_with_payload({"public_key": public_key})


@pytest.fixture
def this_machine(monkeypatch, tmp_path):
    """A machine holding the key for THIS_MACHINE, and nothing in the env."""
    # Own project dir, so the walk-up for `.co` stops here instead of escaping
    # to whatever shared parent the tmp dir happens to sit under.
    (tmp_path / ".co").mkdir()
    monkeypatch.chdir(tmp_path)          # no .env above the test
    monkeypatch.setattr(
        project_cmd_lib.address, "load",
        lambda co_dir: {"address": THIS_MACHINE},
    )
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)


class TestTheTokenNamesAnotherAccount:
    """`~/.env` shadowing `~/.co/keys.env` — the 2026-08-11 incident."""

    def test_the_foreign_token_is_not_returned(self, this_machine, monkeypatch):
        monkeypatch.setenv("OPENONION_API_KEY", token_for(SOMEONE_ELSE))
        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate",
            lambda *a, **k: False,
        )

        returned = load_api_key()

        assert returned != token_for(SOMEONE_ELSE), (
            "load_api_key() handed back a token billing "
            f"{SOMEONE_ELSE[:14]}… while this machine holds the key for "
            f"{THIS_MACHINE[:14]}… — every command downstream now reads that "
            "account's mailbox and spends its credit, with no error shown"
        )

    def test_re_authentication_is_attempted(self, this_machine, monkeypatch):
        """The mismatch is recoverable — the signing key is right here."""
        monkeypatch.setenv("OPENONION_API_KEY", token_for(SOMEONE_ELSE))
        attempts = []

        def authenticate(*args, **kwargs):
            attempts.append(kwargs)
            return False

        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate", authenticate
        )

        load_api_key()

        assert attempts, (
            "no re-authentication was attempted; the CLI holds the key that "
            "would have produced a correct token"
        )


class TestTheOrdinaryCaseIsUndisturbed:
    """The guard costs one local base64 decode when the token is ours."""

    def test_our_own_token_is_returned_unchanged(self, this_machine, monkeypatch):
        ours = token_for(THIS_MACHINE)
        monkeypatch.setenv("OPENONION_API_KEY", ours)

        def authenticate(*args, **kwargs):
            raise AssertionError("re-authenticated for a token already ours")

        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate", authenticate
        )

        assert load_api_key() == ours

    def test_a_token_with_no_account_is_left_alone(self, this_machine, monkeypatch):
        """Not every token is a JWT we can read; an unreadable one is not a mismatch."""
        monkeypatch.setenv("OPENONION_API_KEY", "not-a-jwt")

        def authenticate(*args, **kwargs):
            raise AssertionError("re-authenticated over an undecodable token")

        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate", authenticate
        )

        assert load_api_key() == "not-a-jwt"

    @pytest.mark.parametrize(
        "payload",
        [[], "text", 7, None, {}, {"public_key": []}, {"public_key": 7}],
    )
    def test_a_non_string_account_claim_is_unreadable(
        self, this_machine, monkeypatch, payload
    ):
        """A syntactically valid JSON payload must not crash every CLI call."""
        token = token_with_payload(payload)
        monkeypatch.setenv("OPENONION_API_KEY", token)

        def authenticate(*args, **kwargs):
            raise AssertionError("re-authenticated over an unreadable token")

        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate", authenticate
        )

        assert load_api_key() == token

    def test_no_key_anywhere_still_returns_none(self, this_machine, monkeypatch, tmp_path):
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        assert load_api_key() is None
