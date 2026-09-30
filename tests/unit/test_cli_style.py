"""The one look every co command shares (#1997): styled in a terminal, plain otherwise, same words."""

import io
import re

from rich.console import Console

from connectonion.cli import style

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def render(markup: str, *, terminal: bool) -> str:
    buffer = io.StringIO()
    out = Console(file=buffer, theme=style.THEME, force_terminal=terminal, no_color=not terminal,
                  highlight=False, soft_wrap=True, width=100)
    out.print(markup)
    return buffer.getvalue()


def test_a_next_line_is_styled_in_a_terminal_and_the_same_words_without():
    markup = style.next_line("co rem start")
    styled, plain = render(markup, terminal=True), render(markup, terminal=False)
    assert ANSI.search(styled) and not ANSI.search(plain)
    assert ANSI.sub("", styled) == plain == "Next: co rem start\n"


def test_text_that_looks_like_markup_is_printed_as_written():
    markup = f"Mapped {style.count(3)} people from {style.path('/tmp/[x]/rem')}"
    assert render(markup, terminal=False) == "Mapped 3 people from /tmp/[x]/rem\n"


def test_progress_draws_nothing_off_a_terminal():
    out = Console(file=io.StringIO(), force_terminal=False)
    with style.progress(out) as bar:
        task = bar.add_task("Saving mail", total=3)
        bar.advance(task, 3)
    assert out.file.getvalue() == ""


PAGE = """co proxy — share this computer's internet connection.

  co proxy share [to <address>]   lend your connection to one agent
  co proxy diagnose [<address>]   why a share is not working (else: co proxy share to <address>)

<address> defaults to the one `co remote-browser config` remembered, [not] a cobalt.

Options:
  --ttl SEC       stop after this long

Start with: co proxy share to 0xHOST
Example:  co proxy share to 0xabc... --ttl 3600
Next: co proxy status
Back: co --help"""


def test_a_hand_written_page_prints_word_for_word_off_a_terminal():
    assert render(style.markup(PAGE), terminal=False) == PAGE + "\n"


def test_a_hand_written_page_colours_its_commands_titles_and_next_line_in_a_terminal():
    shown = render(style.markup(PAGE), terminal=True)
    commands = re.findall(r"\x1b\[1;36m(.*?)\x1b\[0m", shown)
    assert commands == ["co proxy", "co proxy share [to <address>]", "co proxy diagnose [<address>]",
                        "co proxy share to <address>", "co remote-browser config", "co proxy share to 0xHOST",
                        "co proxy share to 0xabc... --ttl 3600", "co proxy status", "co --help"]
    assert "\x1b[1;4mOptions:\x1b[0m" in shown
    assert render(style.next_line("co proxy status"), terminal=True) in shown
    assert ANSI.sub("", shown) == PAGE + "\n"
