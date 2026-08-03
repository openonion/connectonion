"""`co status` says "none" about a list it does not cover.

On a machine with four registered servers and two agents running on one of
them, the whole of what `co status` says about deployment is:

    Deployed Agents: none

`_fetch_deployments()` asks ConnectOnion Cloud. Agents put on your own box with
`co deploy --to` live in `~/.co/servers.yaml` and never appear — `co server ls`
lists them, and `co status` does not mention that command or the file.

    $ co server ls
      NAME               TARGET             LAST CHECK   BILLING
      naturewill-prod    naturewill-prod    ok           not ours
      nw-prod            naturewill-test    ok           not ours
      nw-runner          claude-runner      Ubuntu 24.04 not ours
      test               co-test-deploy     never checked not ours

    $ co status | grep -i -e server -e deploy
    Deployed Agents: none

"Status" is the command people run to find out what they have. Answering "none"
to someone with four servers is not a small imprecision; it is the one question
the command exists to answer, answered wrongly.

Nothing here changes what is fetched or shown. The line says which list it is
about, and where the other one lives.
"""

import re
from pathlib import Path

import pytest

from connectonion.cli.commands.status_commands import _show_deployments


def _printed(capsys) -> str:
    return capsys.readouterr().out


class TestTheEmptyLineNamesItsScope:

    def test_it_does_not_claim_there_are_no_agents(self, capsys):
        _show_deployments([])

        line = _printed(capsys)
        assert not re.search(r"Deployed Agents:\s*none\s*$", line.strip()), (
            "the bare 'none' is what reads as 'you have nothing deployed'"
        )

    def test_it_says_which_list_is_empty(self, capsys):
        _show_deployments([])

        assert "cloud" in _printed(capsys).lower()

    def test_it_points_at_the_other_one(self, capsys):
        """Someone who deployed to their own box needs to be told where to look."""
        _show_deployments([])

        assert "co server ls" in _printed(capsys)


class TestNothingElseChanges:

    def test_a_populated_list_is_still_a_table(self, capsys):
        _show_deployments([
            {"project": "billing", "url": "https://billing.example.com",
             "status": "running"},
        ])

        out = _printed(capsys)
        assert "billing" in out

    def test_a_populated_list_does_not_nag_about_servers(self, capsys):
        """The pointer is for the empty case — it answers 'where is mine?'"""
        _show_deployments([
            {"project": "billing", "url": "https://billing.example.com",
             "status": "running"},
        ])

        assert "co server ls" not in _printed(capsys)
