"""`co audit --style` fails each fake CLI for the one thing it gets wrong (#1997).

The rule only reads what a program prints, under a pseudo-terminal and into a
pipe with NO_COLOR, so it is tested on small programs that print: one that
follows the standard, one that is plain everywhere, one that colours a pipe,
one that changes its words in a terminal, and one that dumps internal fields.
They are plain Python with hand-written escape codes, so nothing here depends
on an installed package, the clock or the working directory.
"""

import sys

import pytest

from connectonion.cli import audit
from connectonion.cli.audit import Output, Page

pytest.importorskip("pty")

PRELUDE = r'''
import os, sys
def c(code, text, stream=sys.stdout):
    return f"\033[{code}m{text}\033[0m" if stream.isatty() and not os.environ.get("NO_COLOR") else text
HELP = "--help" in sys.argv
'''

STYLED = PRELUDE + r'''
if HELP:
    print(c(1, "Usage:") + " tool status")
    print("Show whether tool is connected. Read-only.")
    print("Example:  " + c(36, "tool status"))
else:
    print(c(1, "Tool"))
    print("  " + c(32, "✓") + " Gmail connected, " + c(1, "2,113") + " messages")
    print(c(2, "Next:", sys.stderr) + " " + c(36, "tool status --verbose", sys.stderr), file=sys.stderr)
'''

PLAIN_ONLY = PRELUDE + r'''
print("Usage: tool status" if HELP else "Gmail connected")
print("Show whether tool is connected. Read-only.\nExample:  tool status" if HELP else "Next: tool status --verbose")
'''

ALWAYS_COLOURED = PRELUDE + r'''
print("\033[1mUsage:\033[0m tool status\nRead-only.\nExample:  \033[36mtool status\033[0m" if HELP
      else "\033[32m✓\033[0m connected")
'''

OTHER_WORDS = STYLED.replace('" Gmail connected, "', '(" Gmail is connected, " if sys.stdout.isatty() else " Gmail connected, ")')

FIELD_DUMP = STYLED.replace(
    'print("  " + c(32, "✓") + " Gmail connected, " + c(1, "2,113") + " messages")',
    'print("user_id: 42\\nlast_sync_at: 1759200000\\nsyncState: ok\\n{\'raw\': 1}")')


def audit_fake(tmp_path, monkeypatch, source):
    script = tmp_path / "tool.py"
    script.write_text(source)
    monkeypatch.setattr(audit, "program", lambda _: [sys.executable, str(script)])
    help_text = audit.run_plain(["tool", "status", "--help"]).out
    findings, checked = audit.style_audit({"tool status": Page(0, help_text)})
    return {(f.path, f.check) for f in findings}, checked


def test_a_cli_that_follows_the_standard_passes_help_and_run(tmp_path, monkeypatch):
    findings, checked = audit_fake(tmp_path, monkeypatch, STYLED)
    assert set(checked) == {"tool status", "tool status [run]"}
    assert findings == set()


def test_a_cli_that_is_plain_everywhere_is_not_styled(tmp_path, monkeypatch):
    findings, _ = audit_fake(tmp_path, monkeypatch, PLAIN_ONLY)
    assert findings == {("tool status", "styled"), ("tool status", "command_colour"),
                        ("tool status [run]", "styled"), ("tool status [run]", "command_colour")}


def test_a_cli_that_colours_a_pipe_under_no_color_fails_plain(tmp_path, monkeypatch):
    findings, _ = audit_fake(tmp_path, monkeypatch, ALWAYS_COLOURED)
    assert findings == {("tool status", "plain"), ("tool status [run]", "plain")}


def test_a_cli_that_says_other_words_in_a_terminal_fails_same_words(tmp_path, monkeypatch):
    findings, _ = audit_fake(tmp_path, monkeypatch, OTHER_WORDS)
    assert findings == {("tool status [run]", "same_words")}


def test_a_status_that_prints_its_internal_record_is_a_field_dump(tmp_path, monkeypatch):
    findings, _ = audit_fake(tmp_path, monkeypatch, FIELD_DUMP)
    assert findings == {("tool status [run]", "field_dump")}


def test_only_read_only_status_style_leaves_are_run():
    read_only = Page(0, "Usage: tool status\nRead-only.\n")
    assert audit.runnable("co status", read_only)
    assert not audit.runnable("co status", Page(0, "Usage: tool status\nShows status.\n"))
    assert not audit.runnable("co gmail send", Page(0, "Usage: co gmail send\nRead-only.\n"))
    assert not audit.runnable("co server ls", Page(0, "Usage: co server ls\nRead-only.\n\nCommands:\n  all   Every one\n"))


def test_a_spinner_leaves_only_its_last_frame_on_screen():
    raw = "\x1b[?25lworking |\rworking /\r\x1b[2Kline one\nline two\n\x1b[1A\x1b[2Kdone\n"
    assert audit.screen(raw).split() == ["line", "one", "done"]
    terminal, plain = Output(0, "\x1b[1mTool\x1b[0m\r\x1b[2K\x1b[1mTool\x1b[0m ready\n", ""), Output(0, "Tool ready\n", "")
    assert audit.style_check("tool status [run]", terminal, plain) == []


def test_a_command_is_styled_only_where_its_own_characters_are():
    unstyled = "Back: co \x1b[1;36m--help\x1b[0m"
    assert not audit._styled_at(unstyled, len("Back: "))
    assert audit._styled_at("Next: \x1b[36mco auth\x1b[0m", len("Next: "))
    finding = audit.style_check("co x", Output(0, unstyled + "\n", ""), Output(0, "Back: co --help\n", ""))
    assert [f.check for f in finding] == ["command_colour"]


def test_a_run_that_waits_forever_is_killed_and_named(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "RUN_TIMEOUT", 1)
    findings, _ = audit_fake(tmp_path, monkeypatch, STYLED.replace("else:\n", "else:\n    import time; time.sleep(60)\n", 1))
    assert findings == {("tool status [run]", "hangs")}
