"""Every command ends by naming the next one.

An audit on 2026-09-08 walked every `co` command to its last printed line.
Roughly a third ended on a URL, a file path, `✓ done.` or nothing: all seven
`trust` verbs, all of `sms`, most of `skills`, `announce`, `setup`, `eval`,
`init` and `create` (a GitHub link), cloud `deploy` (a dashboard link). The
reader with only that output — usually an agent — has to guess the next
command, and a guessed command name costs a round trip every time.

So the next step is no longer something each handler remembers to print.
_OneSuggestion.invoke runs after every leaf command returns and prints the
entry from command_tips.NEXT. This test makes the table the register:

- every registered leaf has an entry (a tip, or HANDLER when the handler's own
  data-dependent tip is the right one) — a new command cannot ship without one;
- every tip names a command that exists, checked against the tree;
- the tip really is printed, on stderr, after a command returns — and not
  after `--help`, and once (not per nesting level) for a three-deep path.
"""

import pytest
from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.cli.commands import command_tips
from connectonion.cli.commands.command_tips import HANDLER, NEXT, next_step_for
from connectonion.cli.discovery import check, command_tree, commands_in


runner = CliRunner()
LEAVES = [e.path for e in command_tree(cli_main.app) if not e.is_group]


@pytest.mark.parametrize("path", LEAVES)
def test_every_leaf_command_has_an_entry(path):
    try:
        next_step_for(path)
    except KeyError:
        pytest.fail(f"{path} has no entry in command_tips.NEXT — add a tip, "
                    f"or HANDLER if the handler prints its own")


def test_no_entry_is_for_a_command_that_does_not_exist():
    """A stale key is a tip nobody will ever see."""
    leaves = set(LEAVES)
    for key in NEXT:
        if key.endswith(" *"):
            group = key[:-2]
            assert any(p.startswith(group + " ") for p in leaves), key
        else:
            assert key in leaves, f"NEXT has {key!r} but no such command is registered"


@pytest.mark.parametrize("key, tip", [(k, v) for k, v in NEXT.items() if v is not HANDLER])
def test_every_tip_names_exactly_one_real_command(key, tip):
    named = commands_in(tip)
    assert len(named) == 1, f"{key}: a tip names one next command, not {len(named)}: {tip!r}"
    assert check(cli_main.app, named[0]) is None, f"{key}: {check(cli_main.app, named[0])}"


class TestItIsPrinted:

    @pytest.fixture(autouse=True)
    def a_table_with_known_entries(self, monkeypatch):
        # `co trust admin remove` takes an address and, in this test, does
        # nothing else: its handler is replaced so the run is hermetic. The
        # point is the hook, not the handler.
        # raising=True (the default): a wrong name here would silently let the
        # real handler run against whatever .co/ the test happens to be in.
        monkeypatch.setattr(
            "connectonion.cli.commands.trust_commands.handle_admin_remove",
            lambda address: None)
        monkeypatch.setitem(command_tips.NEXT, "co trust admin remove",
                            "See every list:  co trust list")

    def test_after_a_three_deep_command_once_on_stderr(self):
        result = runner.invoke(cli_main.app, ["trust", "admin", "remove", "0xabc"])
        assert result.exit_code == 0, result.output
        err = result.stderr
        assert err.count("Next: See every list:  co trust list") == 1, err
        assert "Next:" not in result.stdout

    def test_not_after_help(self):
        result = runner.invoke(cli_main.app, ["trust", "admin", "remove", "--help"])
        assert result.exit_code == 0
        assert "Next:" not in result.stderr

    def test_handler_entries_print_nothing_here(self, monkeypatch):
        monkeypatch.setitem(command_tips.NEXT, "co trust admin remove", HANDLER)
        result = runner.invoke(cli_main.app, ["trust", "admin", "remove", "0xabc"])
        assert result.exit_code == 0, result.output
        assert "Next:" not in result.stderr


def test_wildcard_resolution_prefers_the_exact_key():
    assert next_step_for("co gmail read") is HANDLER            # via "co gmail *"
    assert next_step_for("co email default") is not HANDLER     # exact
    with pytest.raises(KeyError):
        next_step_for("co nosuchgroup thing")
