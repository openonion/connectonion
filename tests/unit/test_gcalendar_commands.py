"""Calendar CLI parity, preview gates, error recovery, and timezone regressions."""
from pathlib import Path
from unittest.mock import MagicMock
import re
import pytest
from typer.testing import CliRunner
from typer.main import get_command
from connectonion.cli.main import app
from connectonion.cli.commands import gcalendar_commands as commands
from connectonion.useful_tools.google_calendar import GoogleCalendar

READS = [([], 'list_events'), (['list'], 'list_events'), (['today'], 'get_today_events'),
         (['read', 'event-a'], 'get_event'), (['meetings'], 'get_upcoming_meetings'),
         (['free', '2026-09-05'], 'find_free_slots')]
WRITES = [(['create', 'Demo', '2026-09-05T10:00:00Z', '2026-09-05T11:00:00Z'], 'create_event'),
          (['meet', 'Demo', '2026-09-05T10:00:00Z', '2026-09-05T11:00:00Z', '--attendees', 'a@example.invalid'], 'create_meet'),
          (['update', 'event-a', '--title', 'Changed'], 'update_event'), (['delete', 'event-a'], 'delete_event')]

@pytest.mark.parametrize('args,method', READS + WRITES)
def test_dispatch_and_piped_tip(args, method, monkeypatch):
    client = MagicMock()
    getattr(client, method).return_value = 'Event\nID: event-a'
    monkeypatch.setattr(commands, '_client', lambda: client)
    result = CliRunner().invoke(app, ['gcalendar', *args, *(['--yes'] if (args, method) in WRITES else [])])
    assert result.exit_code == 0, result.output
    getattr(client, method).assert_called_once()
    assert result.output.strip().splitlines()[-1].startswith('Next: co gcalendar ')

@pytest.mark.parametrize('args,method', WRITES)
def test_write_preview_never_constructs_client(args, method, monkeypatch):
    monkeypatch.setattr(commands, '_client', lambda: pytest.fail('Preview reached provider'))
    result = CliRunner().invoke(app, ['gcalendar', *args])
    assert result.exit_code == 0 and 'No changes made' in result.output
    assert result.output.strip().endswith(f'co gcalendar {args[0]} --help')

def test_help_skill_parity():
    visible = set(get_command(app).commands['gcalendar'].commands)
    skill = (Path(__file__).resolve().parents[2] / 'connectonion/useful_skills/co-google/SKILL.md').read_text()
    assert visible == set(re.findall(r'co gcalendar ([a-z][a-z-]*)', skill))
    for name in visible:
        assert CliRunner().invoke(app, ['gcalendar', name, '--help']).exit_code == 0

def test_invalid_update_is_actionable():
    result = CliRunner().invoke(app, ['gcalendar', 'update', 'event-a'])
    assert result.exit_code == 2 and 'co gcalendar update --help' in result.output

def test_api_failure_is_sanitized(monkeypatch):
    from googleapiclient.errors import HttpError
    from httplib2 import Response
    client = MagicMock()
    client.list_events.side_effect = HttpError(Response({'status': '403'}), b'PRIVATE')
    monkeypatch.setattr(commands, '_client', lambda: client)
    result = CliRunner().invoke(app, ['gcalendar'])
    assert result.exit_code == 1 and 'PRIVATE' not in result.output and 'co auth google' in result.output

@pytest.mark.parametrize('events,expected', [
    ([{'start': {'dateTime': '2026-09-05T19:00:00+10:00'}, 'end': {'dateTime': '2026-09-05T20:00:00+10:00'}}], '10:00 AM - 05:00 PM'),
    ([{'start': {'date': '2026-09-05'}, 'end': {'date': '2026-09-06'}}], 'No free slots'),
    ([], '09:00 AM - 05:00 PM'),
])
def test_free_slots_handles_timezone_and_all_day(monkeypatch, events, expected):
    monkeypatch.setenv('GOOGLE_SCOPES', 'calendar')
    client = GoogleCalendar()
    client._service = MagicMock()
    client._service.events().list().execute.return_value = {'items': events}
    assert expected in client.find_free_slots('2026-09-05')
