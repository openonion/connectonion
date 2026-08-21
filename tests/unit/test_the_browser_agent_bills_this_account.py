"""`co browser` resolved its own API key, without the account check.

`resolve_api_key()` in `cli/browser_agent/agent.py` is a second implementation of
`load_api_key()`: read the environment, else fall back to `~/.co/keys.env`. What
it does not have is `_token_for_this_account()` — the check that the token in
hand belongs to the account whose key this machine holds.

That matters more here than almost anywhere else, because this is the path that
spends money. `co browser do` runs a natural-language agent, billed to whatever
the token says. The model loop now lives in the caller process, so this lookup
must validate the caller's token on every run before any browser tool is used.

Observed on an operator machine: `co browser click` reporting insufficient
credit on an account with a healthy balance. A `.env` in the working directory
named a different agent — one drained to $0.001 — and the daemon had picked it
up at startup. The error was true; it was about somebody else's balance.

The fix is not a better copy of the lookup. It is to stop having a copy.
"""

import base64
import json
from pathlib import Path

import pytest

from connectonion.cli.browser_agent.agent import resolve_api_key
from connectonion.cli.commands import project_cmd_lib

THIS_MACHINE = "0x" + "10e68f6d" * 8
SOMEONE_ELSE = "0x" + "561605f3" * 8


def token_for(public_key: str) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps({"public_key": public_key}).encode()
    ).decode().rstrip("=")
    return f"header.{payload}.signature"


@pytest.fixture
def this_machine(monkeypatch, tmp_path):
    (tmp_path / ".co").mkdir()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        project_cmd_lib.address, "load",
        lambda co_dir: {"address": THIS_MACHINE},
    )
    monkeypatch.delenv("OPENONION_API_KEY", raising=False)


class TestATokenForAnotherAccount:

    def test_it_is_not_handed_to_the_agent(self, this_machine, monkeypatch):
        monkeypatch.setenv("OPENONION_API_KEY", token_for(SOMEONE_ELSE))
        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate",
            lambda *a, **k: False,
        )

        assert resolve_api_key() != token_for(SOMEONE_ELSE), (
            "the browser agent would run on a token billing "
            f"{SOMEONE_ELSE[:14]}…"
        )

    def test_the_caller_sees_no_key_rather_than_the_wrong_one(
            self, this_machine, monkeypatch):
        """`execute_browser_command` prints 'run co auth' on an empty string."""
        monkeypatch.setenv("OPENONION_API_KEY", token_for(SOMEONE_ELSE))
        monkeypatch.setattr(
            "connectonion.cli.commands.auth_commands.authenticate",
            lambda *a, **k: False,
        )

        assert resolve_api_key() == ""


class TestTheOrdinaryCase:

    def test_our_own_token_is_returned(self, this_machine, monkeypatch):
        ours = token_for(THIS_MACHINE)
        monkeypatch.setenv("OPENONION_API_KEY", ours)

        assert resolve_api_key() == ours

    def test_no_key_is_still_the_empty_string(self, this_machine, monkeypatch, tmp_path):
        """The contract callers rely on: falsy, not None."""
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))

        assert resolve_api_key() == ""
