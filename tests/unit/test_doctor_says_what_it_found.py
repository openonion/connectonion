"""What `co doctor` concludes after finding something wrong.

Run on a real project from a clean install of the wheel:

    user/email-outreach   ✗ broken symlink
    …
    ✅ Diagnostics complete!

    $ echo $?
    0

It found the problem, printed it, and then said everything was fine — in the
one command whose entire job is to tell you whether anything is wrong. People
read the last line, and any script using it as a gate reads the exit code.

Five places add a `✗` row and nothing counted them. So they are counted, the
last line says what was found, and the exit code agrees with the last line.
"""

import pytest

from connectonion.cli.commands.doctor_commands import verdict


class TestTheLastLineAgreesWithTheBody:

    def test_nothing_found_still_says_so(self, capsys):
        assert verdict([]) == 0

        out = capsys.readouterr().out
        assert '✅' in out

    def test_one_problem_is_named_in_the_summary(self, capsys):
        verdict(["user/email-outreach: broken symlink"])

        out = capsys.readouterr().out
        assert 'email-outreach' in out
        assert '✅' not in out, "the summary claimed success over its own finding"

    def test_several_are_all_named(self, capsys):
        verdict(["a: broken symlink", "b: not on PATH", "c: auth failed"])

        out = capsys.readouterr().out
        for name in ('a', 'b', 'c'):
            assert name in out

    def test_the_count_is_stated(self, capsys):
        verdict(["a: x", "b: y"])

        assert '2' in capsys.readouterr().out


class TestAScriptCanUseIt:
    """`co doctor` in a deploy script is the obvious use, and it was useless
    for that: it exits 0 whatever it finds."""

    def test_a_clean_run_exits_zero(self, capsys):
        assert verdict([]) == 0

    def test_a_problem_exits_non_zero(self, capsys):
        assert verdict(["something: wrong"]) == 1


class TestTheExitCodeIsWiredUp:
    """A verdict nothing acts on is a print statement.

    `get_default_trust()` was correct, tested and never called for seven months
    (#366), and this session has already shipped a compaction that nothing
    invoked. So the wiring gets asserted, not assumed.
    """

    def test_the_cli_exits_non_zero_on_problems(self):
        import inspect
        from connectonion.cli import main

        source = inspect.getsource(main.doctor)
        assert 'typer.Exit(1)' in source, (
            "co doctor cannot fail, so a script cannot use it as a gate"
        )
