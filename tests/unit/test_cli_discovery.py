"""Every `co` command can be found from `co` without guessing.

Three levels, each complete at its own level:

    co                     every top-level command   (tested in
                           test_the_first_screen_is_honest.py)
    co commands            every command and subcommand, one per line
    co <group> --help      every subcommand of one group

An agent that cannot find a command from these will invent one, and an
invented name costs a round trip every time. So: nothing hidden, and every
node of the tree reachable from its parent's --help.

Also here: `check()`, the rule the tip sweep uses to decide whether a phrase
like `co gmail open 1` is a command you can run. It is the piece that has to
be right for the sweep to mean anything, so it gets its own cases.
"""

import pytest
import typer.main
from typer.testing import CliRunner

from connectonion.cli import main as cli_main
from connectonion.cli.discovery import Entry, check, command_tree, commands_in


runner = CliRunner()
TREE = command_tree(cli_main.app)


class TestTheTree:

    def test_it_is_not_small(self):
        # ~160 today. The point is that the walk found the nested groups,
        # not a specific number.
        assert len(TREE) > 100

    def test_it_reaches_three_levels_down(self):
        assert any(e.path == "co gmail draft send" for e in TREE)
        assert any(e.path == "co trust admin add" for e in TREE)

    def test_groups_are_marked(self):
        by_path = {e.path: e for e in TREE}
        assert by_path["co gmail"].is_group
        assert by_path["co gmail draft"].is_group
        assert not by_path["co gmail draft send"].is_group
        assert not by_path["co browser"].is_group

    def test_nothing_is_hidden(self):
        """A hidden command is one an agent can only reach by guessing."""
        root = typer.main.get_command(cli_main.app)

        def hidden(cmd, path):
            for name, child in (getattr(cmd, "commands", None) or {}).items():
                if child.hidden:
                    yield " ".join(path + [name])
                yield from hidden(child, path + [name])

        assert list(hidden(root, ["co"])) == []

    def test_summaries_are_one_sentence(self):
        for entry in TREE:
            assert "\n" not in entry.summary, entry
            assert entry.summary, f"{entry.path} has no help text"


class TestEveryNodeIsInItsParentsHelp:
    """`co gmail --help` lists `draft`; `co gmail draft --help` lists `send`."""

    @pytest.mark.parametrize("entry", [e for e in TREE if e.is_group], ids=lambda e: e.path)
    def test_group_help_lists_each_child(self, entry: Entry):
        args = entry.path.split()[1:] + ["--help"]
        result = runner.invoke(cli_main.app, args)
        assert result.exit_code == 0, result.output
        rendered = " ".join(result.output.split())
        children = [e for e in TREE
                    if e.path.startswith(entry.path + " ")
                    and e.path.count(" ") == entry.path.count(" ") + 1]
        missing = [c.path for c in children if c.path.split()[-1] not in rendered]
        assert missing == [], f"{entry.path} --help omits {missing}"


class TestCoCommands:

    @pytest.fixture(scope="class")
    def output(self):
        result = runner.invoke(cli_main.app, ["commands"])
        assert result.exit_code == 0, result.output
        return result.output

    def test_every_path_is_a_line(self, output):
        lines = output.splitlines()
        for entry in TREE:
            assert any(line.startswith(entry.path + " ") for line in lines), entry.path

    def test_each_line_carries_the_summary(self, output):
        for entry in TREE:
            assert entry.summary in output, entry

    def test_it_is_plain_text(self, output):
        # The audience is a pipe: `co commands | grep draft`.
        assert "\x1b[" not in output
        assert "[green]" not in output

    def test_it_names_the_two_surfaces_it_cannot_list(self, output):
        assert "co <command> --help" in output
        assert "co browser help" in output


class TestCheck:
    """The group/leaf rule: at a group the next word must be a subcommand;
    at a leaf anything goes, because leaves parse their own arguments."""

    @pytest.mark.parametrize("phrase", [
        "co status",
        "co gmail",                       # bare group: shows the inbox
        "co gmail read",
        "co gmail draft send",
        "co browser tab ls",              # browser is a leaf with its own verbs
        "co browser go_to",
        "co call",
        "co gmail --json",                # a flag on the group itself
    ])
    def test_real_commands_pass(self, phrase):
        assert check(cli_main.app, phrase) is None

    @pytest.mark.parametrize("phrase, reason", [
        ("co gmail open", "no subcommand `open`"),
        ("co gmail to", "no subcommand `to`"),         # "run co gmail to refresh"
        ("co gmail draft mail", "no subcommand `mail`"),
        ("co readmail", "no subcommand `readmail`"),
        ("gmail read", "does not start with `co`"),
    ])
    def test_invented_commands_fail_with_the_reason(self, phrase, reason):
        verdict = check(cli_main.app, phrase)
        assert verdict is not None and reason in verdict, verdict

    def test_the_reason_lists_what_exists(self):
        assert "read" in check(cli_main.app, "co gmail open")


class TestCommandsIn:
    """What a tip names, as the sweep will read it."""

    def test_stops_at_placeholders_flags_and_numbers(self):
        assert commands_in("Read one with: co gmail read <#>") == ["co gmail read"]
        assert commands_in("Next: co server check {name}") == ["co server check"]
        assert commands_in("co browser --headless go_to") == ["co browser"]
        assert commands_in("co gmail read 3") == ["co gmail read"]

    def test_finds_every_phrase_in_a_line(self):
        assert commands_in("co server check {name}  ·  co deploy --to {name}") == [
            "co server check", "co deploy"]

    def test_does_not_match_look_alikes(self):
        assert commands_in("co-ai template, co/gemini-3.7-flash, Cisco gear, .co/keys.env") == []

    def test_prose_with_no_command_names_nothing(self):
        assert commands_in("See the docs for more options") == []
