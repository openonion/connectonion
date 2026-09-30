"""`co <inbox> check` is in the palette, with no auto-highlighting (#2008).

Rich's default highlighter coloured `co whatsapp check`'s session path in two
magentas and any date or number in bold cyan pieces, so the same line looked
different depending on what it happened to contain.
"""

import re
from types import SimpleNamespace

import pytest

from connectonion.cli.commands import listen_commands

SGR = re.compile(r"\x1b\[[0-9;]*m")


def _check(monkeypatch, capsys, problem):
    monkeypatch.setenv("FORCE_COLOR", "1")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(listen_commands, "console", listen_commands.style.console())   # read at construction
    monkeypatch.setattr(listen_commands, "provider", lambda name: SimpleNamespace(check=lambda: [problem]))
    with pytest.raises(SystemExit):
        listen_commands.handle_check("whatsapp")
    return capsys.readouterr().out


def test_a_path_and_a_date_are_not_coloured_in_pieces(monkeypatch, capsys):
    out = _check(monkeypatch, capsys, "No linked session at /tmp/x/session.db since 2026-10-01.")
    first = out.splitlines()[0]
    assert "/tmp/x/session.db since 2026-10-01." in first     # no escape code inside either
    assert SGR.search(first)                                   # the ✗ is still the error colour


def test_the_next_step_is_its_own_next_line(monkeypatch, capsys):
    out = _check(monkeypatch, capsys, "No linked session. Next: co whatsapp listen — scan the QR code.")
    plain = SGR.sub("", out).splitlines()
    assert plain == ["✗ No linked session.", "Next: co whatsapp listen — scan the QR code."]
