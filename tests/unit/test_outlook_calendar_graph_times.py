"""Outlook calendar reads real Graph times on every supported Python (#1717).

LLM-Note: Tests for connectonion/useful_tools/microsoft_calendar.py and
connectonion/cli/commands/microsoft_errors.py

Microsoft Graph writes event times with seven fractional-second digits
("2026-09-28T06:00:00.0000000"). `datetime.fromisoformat` takes three or six
before Python 3.11, so on 3.10 — which pyproject supports — every calendar read
failed once the calendar held one event, and the CLI said the user's
arguments were wrong. The older tests fed "…T10:00:00Z", which no Graph
response contains, so they passed on 3.10 too.
"""

import os
from unittest.mock import MagicMock, patch

import pytest
import typer

GRAPH_START = "2026-09-28T06:00:00.0000000"
GRAPH_END = "2026-09-28T07:00:00.0000000"
ENV = {
    "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
    "MICROSOFT_ACCESS_TOKEN": "test-token",
    "MICROSOFT_REFRESH_TOKEN": "test-refresh",
    "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z",
}


def _graph_returns(mock_httpx, events):
    response = MagicMock(status_code=200)
    response.json.return_value = {"value": events}
    mock_httpx.request.return_value = response


def _event(subject="Standup", start=GRAPH_START, end=GRAPH_END):
    return {"id": "e1", "subject": subject, "attendees": [],
            "start": {"dateTime": start, "timeZone": "UTC"},
            "end": {"dateTime": end, "timeZone": "UTC"}}


@pytest.mark.parametrize("value, expected", [
    (GRAPH_START, (6, 0, 0)),
    ("2026-09-28T06:00:00.1234567", (6, 0, 123456)),
    ("2026-09-28T06:00:00.5", (6, 0, 500000)),
    ("2026-09-28T06:00:00Z", (6, 0, 0)),
    ("2026-09-28T06:00:00.0000000+10:00", (6, 0, 0)),
])
def test_every_fraction_graph_or_a_person_writes_parses(value, expected):
    from connectonion.useful_tools.microsoft_calendar import _graph_datetime

    parsed = _graph_datetime(value)

    assert (parsed.hour, parsed.minute, parsed.microsecond) == expected


@patch("connectonion.useful_tools.microsoft_calendar.httpx")
def test_listing_a_real_graph_event_shows_it(mock_httpx):
    _graph_returns(mock_httpx, [_event()])
    with patch.dict(os.environ, ENV, clear=False):
        from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
        result = MicrosoftCalendar().list_events(days_ahead=7)

    assert "Standup" in result
    assert "2026-09-28 06:00 AM" in result


@patch("connectonion.useful_tools.microsoft_calendar.httpx")
def test_free_slots_read_real_graph_events(mock_httpx):
    _graph_returns(mock_httpx, [_event(start="2026-09-28T10:00:00.0000000",
                                       end="2026-09-28T11:00:00.0000000")])
    with patch.dict(os.environ, ENV, clear=False):
        from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
        result = MicrosoftCalendar().find_free_slots("2026-09-28", duration_minutes=30)

    assert "09:00 AM - 10:00 AM" in result
    assert "11:00 AM - 05:00 PM" in result


def test_a_local_error_is_reported_as_itself_not_as_bad_input(capsys):
    from connectonion.cli.commands.microsoft_errors import microsoft_errors

    @microsoft_errors("co outlook calendar list")
    def handler():
        raise ValueError("Invalid isoformat string: '2026-09-28T06:00:00.0000000'")

    with pytest.raises(typer.Exit):
        handler()

    err = capsys.readouterr().err
    assert "Invalid isoformat string" in err
    assert "check the command arguments" not in err
