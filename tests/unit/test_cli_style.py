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
