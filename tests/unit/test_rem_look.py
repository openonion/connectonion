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
