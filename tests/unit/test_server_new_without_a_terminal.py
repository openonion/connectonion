"""The one command that spends money must not die on a traceback.

`co server new` charges twelve months up front. Asked to confirm on a stdin
that cannot be polled — CI, a script, an agent driving the CLI — prompt_toolkit
registered the file descriptor with asyncio and raised

    OSError: [Errno 22] Invalid argument

as a bare traceback, saying nothing about whether anything had been charged.
"""

import sys
from unittest.mock import patch

from connectonion.cli.commands import server_commands as sc


PRICING = {
    "region": "australia-southeast1",
    "term_months": 12,
    "machine_types": {
        "e2-small": {
            "usd_12mo": 360.0,
            "usd_month": 30.0,
            "description": "2 vCPU (shared), 2 GB",
        }
    },
}


def confirm_without_a_tty(capsys):
    with patch.object(sys.stdin, "isatty", return_value=False):
        with patch("questionary.confirm") as prompt:
            answer = sc._confirm("my-box", "e2-small", PRICING, balance=1000.0)
    return answer, prompt, capsys.readouterr().out


def test_it_declines_instead_of_crashing(capsys):
    answer, _, _ = confirm_without_a_tty(capsys)

    assert answer is False, "a spend must not be approved by a prompt nobody answered"


def test_it_never_reaches_the_prompt(capsys):
    _, prompt, _ = confirm_without_a_tty(capsys)

    assert not prompt.called, (
        "questionary was called on a stdin that cannot be polled — "
        "that is the OSError"
    )


def test_it_says_what_to_do_and_what_it_costs(capsys):
    _, _, out = confirm_without_a_tty(capsys)

    assert "--yes" in out, "the way to proceed is not named"
    assert "360" in out, "the amount at stake is not repeated in the error"
