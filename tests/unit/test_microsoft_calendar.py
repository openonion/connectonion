"""Test the MicrosoftCalendar tool functionality."""

import os
import pytest
from unittest.mock import patch, MagicMock


class TestMicrosoftCalendarInit:
    """Test MicrosoftCalendar initialization."""

    def test_calendar_requires_microsoft_scopes(self):
        """Test that MicrosoftCalendar raises error when scopes are missing."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": ""}, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            with pytest.raises(ValueError) as exc_info:
                MicrosoftCalendar()
            assert "Missing Microsoft Calendar scopes" in str(exc_info.value)
            assert "co auth microsoft" in str(exc_info.value)

    def test_calendar_init_with_valid_scopes(self):
        """Test that MicrosoftCalendar initializes with valid scopes."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite"}, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            assert calendar._access_token is None


class TestMicrosoftCalendarTokenManagement:
    """Test MicrosoftCalendar token management."""

    def test_get_access_token_requires_credentials(self):
        """Test that getting token requires credentials."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "",
            "MICROSOFT_REFRESH_TOKEN": ""
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            with pytest.raises(ValueError) as exc_info:
                calendar._get_access_token()
            assert "credentials not found" in str(exc_info.value)

    def test_get_access_token_returns_valid_token(self):
        """Test that valid token is returned."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            token = calendar._get_access_token()
            assert token == "test-token"


class TestMicrosoftCalendarDateTimeParsing:
    """Test datetime parsing utilities."""

    def test_parse_time_iso_format(self):
        """Test parsing ISO format datetime."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite"}, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()

            dt = calendar._parse_time("2024-01-15T14:00:00Z")
            assert dt.year == 2024
            assert dt.month == 1
            assert dt.day == 15
            assert dt.hour == 14

    def test_parse_time_simple_format(self):
        """Test parsing simple datetime format."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite"}, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()

            dt = calendar._parse_time("2024-01-15 14:00")
            assert dt.year == 2024
            assert dt.month == 1
            assert dt.day == 15
            assert dt.hour == 14

    def test_parse_time_invalid_format(self):
        """Test parsing invalid datetime format raises error."""
        with patch.dict(os.environ, {"MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite"}, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()

            with pytest.raises(ValueError) as exc_info:
                calendar._parse_time("invalid-time")
            assert "Cannot parse time" in str(exc_info.value)


class TestMicrosoftCalendarReadOperations:
    """Test MicrosoftCalendar read operations with mocked API."""

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_list_events(self, mock_httpx):
        """Test listing calendar events."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'value': [
                {
                    'id': 'event-1',
                    'subject': 'Team Meeting',
                    'start': {'dateTime': '2024-01-15T10:00:00Z'},
                    'end': {'dateTime': '2024-01-15T11:00:00Z'},
                    'attendees': [
                        {'emailAddress': {'address': 'alice@example.com'}}
                    ],
                    'onlineMeetingUrl': 'https://teams.microsoft.com/l/meetup-join/...'
                }
            ]
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.list_events(days_ahead=7)

            assert "Team Meeting" in result
            assert "alice@example.com" in result

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_get_today_events_empty(self, mock_httpx):
        """Test getting today's events when none exist."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'value': []}
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.get_today_events()

            assert "No events scheduled for today" in result


class TestMicrosoftCalendarCreateOperations:
    """Test MicrosoftCalendar create operations with mocked API."""

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_create_event(self, mock_httpx):
        """Test creating a calendar event."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'new-event-123',
            'subject': 'New Meeting',
            'webLink': 'https://outlook.office.com/calendar/...'
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.create_event(
                title="New Meeting",
                start_time="2024-01-15 14:00",
                end_time="2024-01-15 15:00"
            )

            assert "Event created" in result
            assert "New Meeting" in result

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_create_teams_meeting(self, mock_httpx):
        """Test creating a Teams meeting."""
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {
            'id': 'teams-meeting-123',
            'subject': 'Teams Sync',
            'onlineMeetingUrl': 'https://teams.microsoft.com/l/meetup-join/...'
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.create_teams_meeting(
                title="Teams Sync",
                start_time="2024-01-15 14:00",
                end_time="2024-01-15 15:00",
                attendees="alice@example.com,bob@example.com"
            )

            assert "Teams meeting created" in result
            assert "Teams Sync" in result


class TestMicrosoftCalendarUpdateDeleteOperations:
    """Test MicrosoftCalendar update and delete operations."""

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_update_event(self, mock_httpx):
        """Test updating a calendar event."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'event-123',
            'subject': 'Updated Meeting'
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.update_event(
                event_id="event-123",
                title="Updated Meeting"
            )

            assert "Event updated" in result

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_delete_event(self, mock_httpx):
        """Test deleting a calendar event."""
        mock_response = MagicMock()
        mock_response.status_code = 204
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.delete_event("event-123")

            assert "Event deleted" in result
            assert "event-123" in result


class TestMicrosoftCalendarAvailability:
    """Test MicrosoftCalendar availability checking."""

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_check_availability_free(self, mock_httpx):
        """Test checking availability when time is free."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'value': []}
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.check_availability("2024-01-15 14:00")

            assert "FREE" in result

    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_check_availability_busy(self, mock_httpx):
        """Test checking availability when time is busy."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'value': [
                {
                    'subject': 'Existing Meeting',
                    'start': {'dateTime': '2024-01-15T14:00:00Z'}
                }
            ]
        }
        mock_httpx.request.return_value = mock_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "MICROSOFT_ACCESS_TOKEN": "test-token",
            "MICROSOFT_REFRESH_TOKEN": "test-refresh",
            "MICROSOFT_TOKEN_EXPIRES_AT": "2099-12-31T23:59:59Z"
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            result = calendar.check_availability("2024-01-15 14:00")

            assert "BUSY" in result
            assert "Existing Meeting" in result
