"""One `Next:` per run, in every state `check` can report.

The next-step table prints a tip after a command returns, and a handler that
prints its own gets `HANDLER` in the table so the two do not stack. `check`
grew branch-dependent tips and kept its fixed table entry, so a run with no
listener printed:

    Next: co whatsapp listen
    Next: co whatsapp listen

and the branch that tells you to read the log printed two *different* tips —
a fork an agent resolves by guessing, and it reads the worse one first because
stderr is what most callers merge in front.

tests/unit/test_every_command_has_a_next_step.py asserts at least one, which is
why it stayed green through all of it. This file asserts exactly one.
"""

import json

import pytest

from connectonion.cli.commands import listen_commands
from connectonion.inbox import Inbox


class FakeProvider:
    def check(self):
        return []


@pytest.fixture
def box(tmp_path, monkeypatch):
    monkeypatch.setenv("CO_INBOX_HOME", str(tmp_path / "inbox"))
    monkeypatch.setattr(listen_commands, "provider", lambda name: FakeProvider())
    return Inbox("whatsapp")


def next_lines(capsys) -> list:
    captured = capsys.readouterr()
    return [line for line in (captured.out + captured.err).splitlines()
            if line.strip().startswith("Next:")]


def run_check():
    try:
        listen_commands.handle_check("whatsapp")
    except SystemExit:
        pass


def pin(box, state: str, pid: int, **detail):
    box.record_connection(state, **detail)
    record = json.loads(box.connection.read_text())
    record["pid"] = pid
    box.connection.write_text(json.dumps(record))


def test_no_listener_names_one_next_step(box, capsys):
    run_check()
    assert next_lines(capsys) == ["Next: co whatsapp listen"]


def test_a_connected_listener_names_one_next_step(box, capsys, monkeypatch):
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
    pin(box, "connected", 4242, account="61410724095")

    run_check()

    assert next_lines(capsys) == ["Next: co whatsapp receive"]


def test_a_listener_that_has_not_said_names_one_next_step(box, capsys, monkeypatch):
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
    box.record_connection("connected", account="61410724095")   # records os.getpid()

    run_check()

    assert next_lines(capsys) == ["Next: co whatsapp log"]


def test_a_disconnected_listener_names_one_next_step(box, capsys, monkeypatch):
    monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
    pin(box, "disconnected", 4242)

    run_check()

    assert next_lines(capsys) == ["Next: co whatsapp log"]


def test_the_table_leaves_check_to_its_handler():
    """The other half of the fix: a fixed tip here would stack on those."""
    from connectonion.cli.commands.command_tips import HANDLER, next_step_for

    for provider in ("feishu", "lark", "whatsapp"):
        assert next_step_for(f"co {provider} check") is HANDLER


def test_the_whole_command_prints_one_next_step(box, monkeypatch):
    """Through the real entry point, which is where the two halves met.

    The tests above drive the handler, and the handler alone was never wrong.
    The duplicate came from the table firing on top of it in
    `_OneSuggestion.invoke`, so it only appears when the command is invoked the
    way a person invokes it.

    It has to be the connected branch. The others end in `sys.exit(3)`, and a
    handler that raises never returns to `invoke`, so the table is skipped and
    the duplicate cannot happen there however the table is set — a test on one
    of those branches would pass with the bug fully in place.
    """
    from typer.testing import CliRunner

    from connectonion.cli import main as cli_main
    from connectonion.cli.commands import command_tips

    monkeypatch.setattr(Inbox, "listener_pid", lambda self: 4242)
    pin(box, "connected", 4242, account="61410724095")
    command_tips.forget_next_step_named()

    result = CliRunner().invoke(cli_main.app, ["whatsapp", "check"])

    printed = [line for line in result.output.splitlines() if line.strip().startswith("Next:")]
    assert printed == ["Next: co whatsapp receive"], result.output
