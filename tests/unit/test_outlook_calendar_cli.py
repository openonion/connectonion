"""`co outlook calendar`: the Microsoft half of #816, shaped like `co gcalendar`.

Outlook is one product with three panes — Mail, Calendar, People — so the
calendar lives under `co outlook`, beside `contact`, rather than as a fourth
top-level name an agent would have to guess. Every leaf maps to one
MicrosoftCalendar method; writes preview by default and the preview prints the
exact command that performs them.
"""
from pathlib import Path
from unittest.mock import MagicMock
import os
import re

import pytest
from rich.text import Text
from typer.main import get_command
from typer.testing import CliRunner

from connectonion.cli.main import app
from connectonion.cli.commands import outlook_calendar_commands as commands

READS = [([], 'list_events'), (['list'], 'list_events'), (['today'], 'get_today_events'),
         (['read', 'event-a'], 'get_event'), (['meetings'], 'get_upcoming_meetings'),
         (['free', '2026-09-10'], 'find_free_slots')]
WRITES = [(['create', 'Demo', '2026-09-10T10:00:00Z', '2026-09-10T11:00:00Z'], 'create_event'),
          (['teams', 'Demo', '2026-09-10T10:00:00Z', '2026-09-10T11:00:00Z', '--attendees', 'a@example.invalid'], 'create_teams_meeting'),
          (['update', 'event-a', '--title', 'Changed'], 'update_event'),
          (['delete', 'event-a'], 'delete_event')]


def plain(output: str) -> str:
    return Text.from_ansi(output).plain


@pytest.mark.parametrize('args,method', READS + WRITES)
def test_dispatch_and_piped_tip(args, method, monkeypatch):
    client = MagicMock()
    getattr(client, method).return_value = 'Event\n   ID: event-a'
    monkeypatch.setattr(commands, '_client', lambda: client)
    result = CliRunner().invoke(app, ['outlook', 'calendar', *args, *(['--yes'] if (args, method) in WRITES else [])])
    assert result.exit_code == 0, result.output
    getattr(client, method).assert_called_once()
    assert plain(result.output).strip().splitlines()[-1].startswith('Next: co outlook calendar ')


def test_list_tip_names_the_first_event_id(monkeypatch):
    client = MagicMock()
    client.list_events.return_value = 'Upcoming events:\n- 2026-09-10 10:00 AM: Demo\n   ID: AAMkAGI2-event=\n'
    monkeypatch.setattr(commands, '_client', lambda: client)
    result = CliRunner().invoke(app, ['outlook', 'calendar'])
    assert plain(result.output).strip().splitlines()[-1] == 'Next: co outlook calendar read AAMkAGI2-event='


@pytest.mark.parametrize('args,method', WRITES)
def test_write_preview_prints_the_exact_command_that_performs_it(args, method, monkeypatch):
    monkeypatch.setattr(commands, '_client', lambda: pytest.fail('Preview reached provider'))
    result = CliRunner().invoke(app, ['outlook', 'calendar', *args])
    output = plain(result.output)
    assert result.exit_code == 0 and 'No changes made' in output
    last = output.strip().splitlines()[-1]
    assert last.startswith(f'Next: co outlook calendar {args[0]} ') and last.endswith(' --yes')
    for value in args[1:]:
        assert value in last


@pytest.mark.parametrize('path', [('outlook',), ('outlook', 'contact'), ('outlook', 'calendar')])
def test_help_and_skill_parity(path):
    command = get_command(app)
    for name in path:
        command = command.commands[name]
    visible = {name for name, child in command.commands.items() if not child.hidden}
    skill = (Path(__file__).resolve().parents[2] / 'connectonion/useful_skills/co-mail-and-drive/SKILL.md').read_text()
    documented = set(re.findall(r'co ' + ' '.join(path) + r' ([a-z][a-z-]*)', skill))
    assert visible == documented, (visible ^ documented)
    result = CliRunner().invoke(app, [*path, '--help'])
    assert result.exit_code == 0
    for name in visible:
        assert re.search(r'\b' + name + r'\b', plain(result.output))
        assert CliRunner().invoke(app, [*path, name, '--help']).exit_code == 0


def test_invalid_update_is_actionable():
    result = CliRunner().invoke(app, ['outlook', 'calendar', 'update', 'event-a'])
    assert result.exit_code == 2 and 'co outlook calendar update --help' in plain(result.output)


def test_graph_failure_is_sanitized_and_recoverable(monkeypatch):
    from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
    env = {"MICROSOFT_ACCESS_TOKEN": "t", "MICROSOFT_REFRESH_TOKEN": "r",
           "MICROSOFT_SCOPES": "Calendars.ReadWrite", "MICROSOFT_TOKEN_EXPIRES_AT": "2099-01-01T00:00:00Z"}
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    failed = MagicMock(status_code=500, text='PRIVATE tenant detail')
    monkeypatch.setattr('connectonion.useful_tools.microsoft_calendar.httpx.request', lambda *a, **k: failed)
    monkeypatch.setattr(commands, '_client', MicrosoftCalendar)
    result = CliRunner().invoke(app, ['outlook', 'calendar'])
    output = plain(result.output)
    assert result.exit_code == 1 and 'PRIVATE' not in output
    assert re.search(r'^Next: co ', output, re.MULTILINE)


def test_missing_calendar_scope_asks_for_reconsent(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("AGENT_CONFIG_PATH", str(tmp_path / ".co"))
    for key, value in {"MICROSOFT_ACCESS_TOKEN": "t", "MICROSOFT_SCOPES": "Mail.Read,Mail.Send"}.items():
        monkeypatch.setenv(key, value)
    result = CliRunner().invoke(app, ['outlook', 'calendar'])
    output = plain(result.output)
    assert result.exit_code == 1
    assert 'Calendars' in output and re.search(r'^Next: co auth microsoft$', output, re.MULTILINE)


@pytest.mark.parametrize('given,expected', [
    ('2026-09-10T20:00:00+10:00', '2026-09-10T10:00:00'),
    ('2026-09-10T10:00:00Z', '2026-09-10T10:00:00'),
    ('2026-09-10 10:00', '2026-09-10T10:00:00'),
])
def test_offsets_normalize_to_utc_and_naive_means_utc(given, expected, monkeypatch):
    from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
    monkeypatch.setenv("MICROSOFT_SCOPES", "Calendars.ReadWrite")
    monkeypatch.setenv("MICROSOFT_ACCESS_TOKEN", "t")
    assert MicrosoftCalendar()._parse_time(given).isoformat() == expected
