"""co rem's words in the shared palette never change a word (#1996)."""

import io
import re

import pytest
from rich.console import Console
from rich.text import Text

from connectonion.cli import style
from connectonion.cli.commands import rem_look
from connectonion.cli.commands.rem_help import pages

TRICKY = ["Next:     co rem open   (read your page), then co rem start (keep it current)",
          r"co rem reflect people/a.md \\", "a path [x]/rem/people/[bob].md and a:x:b", "ends in \\\\",
          "Error: mailbox gmail failed [TimeoutError]", "Stopped:", "Warning: 3 messages in [brackets]"]


def styled(markup):
    out = Console(file=io.StringIO(), theme=style.THEME, force_terminal=True, width=300, soft_wrap=True)
    out.print(markup, emoji=False)
    return re.sub(r"\x1b\[[0-9;]*m", "", out.file.getvalue())


@pytest.mark.parametrize("line", TRICKY + sorted({line for text in pages().values() for line in text.split("\n")}))
def test_every_line_keeps_its_words_as_markup(line):
    for markup in (rem_look.highlight(line, counts=True), rem_look.page(line), rem_look.result(line, titled=False)):
        assert Text.from_markup(markup, emoji=False).plain == line
        assert styled(markup) == line + "\n"


def test_a_command_is_styled_as_far_as_it_goes_and_no_further():
    markup = rem_look.highlight("nothing is read until co rem start is approved; see co rem investigate people/a.md.")
    commands = re.findall(r"\[co\.command\](.*?)\[/co\.command\]", markup)
    assert commands == ["co rem start", "co rem investigate people/a.md"]


def test_a_help_page_marks_its_sections_and_its_command_column():
    markup = rem_look.page(pages()["co rem"])
    for heading in ("Build (once)", "Read", "Keep it current", "Settings", "Options (before the command):"):
        assert f"[co.heading]{heading}[/co.heading]" in markup
    assert "  [co.command]init[/co.command]" in markup and "[co.command]co rem init[/co.command]" in markup


# ------------------------------------------------- the shared layout (1.9.0a9)


def test_a_long_value_wraps_under_its_own_column_in_an_80_column_terminal():
    """A long value wrapped to column 0 and broke the column it sat in."""
    row = rem_look.row("Outlook", "connected, but not read by the daily round (not subscribed) and more words here",
                       style.warn(rem_look.BROKEN))
    lines = Text.from_markup(rem_look.hang(row, 80)).plain.split("\n")
    assert len(lines) == 2 and all(len(line) <= 80 for line in lines)
    assert lines[1].startswith(" " * rem_look.COLUMN) and not lines[1][rem_look.COLUMN].isspace()
    assert " ".join(" ".join(lines).split()) == " ".join(Text.from_markup(row).plain.split())
    short = rem_look.row("Gmail", "read by the daily round", style.ok(rem_look.FINE))
    assert rem_look.hang(short, 80) == short


def test_the_glyph_layout_keeps_its_words_in_a_terminal_and_in_a_pipe():
    markup = "\n".join([rem_look.section("Today", "3 runs"), rem_look.row("People", rem_look.meter(46, 312)),
                        rem_look.follow(style.command("co rem start"))])
    plain = Text.from_markup(markup).plain
    assert styled(markup) == plain + "\n"
    assert plain.split("\n") == ["Today            3 runs", "  People         ●○○○○○○○○○",
                                 "                 → co rem start"]


@pytest.mark.parametrize("done,total,dots", [(0, 312, 0), (1, 330, 1), (46, 312, 1), (311, 312, 9), (154, 154, 10),
                                             (0, 0, 0)])
def test_the_meter_shows_anything_written_and_is_full_only_when_all_of_it_is(done, total, dots):
    assert Text.from_markup(rem_look.meter(done, total)).plain.count(rem_look.WRITTEN) == dots


def test_tokens_read_as_a_person_reads_them():
    assert [rem_look.compact(n) for n in (812, 91_234, 999_499, 999_999, 1_706_683)] == \
        ["812", "91k", "999k", "1.0M", "1.7M"]


def test_a_sync_step_hangs_its_outcome_in_the_margin(capsys):
    for text in ("Investigating people/a.md…", "Updated people/a.md (accepted)", "Refused people/b.md: too long",
                 "Nothing new for people/c.md", "New material: 3 items, 1 pages changed (completed)"):
        rem_look.step(text, err=False)
    assert capsys.readouterr().out.splitlines() == [
        "  Investigating people/a.md…", "✓ Updated people/a.md (accepted)", "✗ Refused people/b.md: too long",
        "○ Nothing new for people/c.md", "  New material: 3 items, 1 pages changed (completed)"]
