"""Edit, delete and react say they refuse on a provider that cannot do them.

Every inbox group has the same verbs, and their help used to be the same too:
"Prints the edit's id" on Discord, Telegram, Feishu and Lark, where the command
only prints that it is not implemented (found testing 1.8.8b7). The CLI's
`writes=` flag is checked here against what each provider class really has,
so the two cannot drift.
"""

import importlib
import re

import pytest
from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.inbox import PROVIDERS

VERB_METHOD = {"edit": "edit", "delete": "revoke", "react": "react"}


def help_line(group: str, verb: str) -> str:
    page = CliRunner().invoke(cli_main.app, [group, "--help"], env={"COLUMNS": "200"}).output
    for line in re.sub(r"\x1b\[[0-9;]*m", "", page).splitlines():
        words = line.replace("│", " ").split()
        if words and words[0] == verb:
            return line
    raise AssertionError(f"co {group} --help does not list {verb}")


@pytest.mark.parametrize("group", sorted(PROVIDERS))
@pytest.mark.parametrize("verb", sorted(VERB_METHOD))
def test_the_help_matches_what_the_provider_can_do(group, verb):
    module, cls, _ = PROVIDERS[group]
    can = callable(getattr(getattr(importlib.import_module(module), cls), VERB_METHOD[verb], None))
    line = help_line(group, verb)
    assert ("Not implemented" in line) is (not can), line
