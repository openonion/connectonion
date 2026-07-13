"""Test the MicrosoftCalendar tool functionality."""
"""
LLM-Note: Tests for microsoft calendar

What it tests:
- Microsoft Calendar functionality

Components under test:
- Module: microsoft_calendar
"""


import os
from hashlib import sha256
import httpx
import pytest
from unittest.mock import patch, MagicMock


@pytest.fixture(autouse=True)
def _stub_token_fetch(request, monkeypatch):
    """Keep Graph-operation tests isolated from the oo-api token endpoint."""
    if "token_fetch" in request.keywords:
        return
    from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
    monkeypatch.setattr(
        MicrosoftCalendar,
        "_fetch_access_token",
        lambda self, rejected_access_token=None: "test-token",
    )


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

    @pytest.mark.token_fetch
    def test_get_access_token_requires_openonion_auth(self):
        """The client needs only an OpenOnion API key, not Microsoft tokens."""
        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "OPENONION_API_KEY": "",
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            with pytest.raises(ValueError) as exc_info:
                calendar._get_access_token()
            assert "co auth" in str(exc_info.value)

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_first_use_fetches_once_without_a_request_body(self, mock_httpx):
        """First use asks oo-api once; later uses reuse only instance memory."""
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "access_token": "server-access",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "OPENONION_API_KEY": "api-key",
            "OPENONION_API_URL": "https://oo.example",
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            assert calendar._get_access_token() == "server-access"
            assert calendar._get_access_token() == "server-access"

        mock_httpx.post.assert_called_once_with(
            "https://oo.example/api/v1/oauth/microsoft/refresh",
            headers={"Authorization": "Bearer api-key"},
        )

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_cae_28_hour_access_token_is_accepted(self, mock_httpx):
        """Microsoft documents 20-28 hour CAE access-token lifetimes."""
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "access_token": "cae-access",
            "expires_in": 28 * 60 * 60,
        }
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.ReadWrite",
            "OPENONION_API_KEY": "api-key",
        }, clear=False), patch(
            "connectonion.useful_tools.microsoft_calendar.time.monotonic",
            return_value=1000,
        ):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            assert calendar._get_access_token() == "cae-access"
            assert calendar._access_token_refresh_at == 1000 + 28 * 60 * 60 - 300

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_implausible_access_token_lifetime_is_rejected(self, mock_httpx):
        response = MagicMock(status_code=200)
        response.json.return_value = {
            "access_token": "bad-access",
            "expires_in": 48 * 60 * 60 + 1,
        }
        mock_httpx.post.return_value = response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.ReadWrite",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            with pytest.raises(ValueError, match="invalid Microsoft token response"):
                MicrosoftCalendar()._get_access_token()

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_access_token_is_refetched_five_minutes_before_expiry(self, mock_httpx):
        first = MagicMock(status_code=200)
        first.json.return_value = {
            "access_token": "first-access",
            "expires_in": 3600,
        }
        second = MagicMock(status_code=200)
        second.json.return_value = {
            "access_token": "second-access",
            "expires_in": 3600,
        }
        mock_httpx.post.side_effect = [first, second]

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "OPENONION_API_KEY": "api-key",
        }, clear=False), patch(
            "connectonion.useful_tools.microsoft_calendar.time.monotonic",
            side_effect=[1000, 4299, 4300, 4300],
        ):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            assert calendar._get_access_token() == "first-access"
            assert calendar._get_access_token() == "first-access"
            assert calendar._get_access_token() == "second-access"

        assert mock_httpx.post.call_count == 2

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_graph_401_reports_rejected_token_and_retries_once(self, mock_httpx):
        """A Graph 401 triggers one server refresh tied to the rejected token."""
        first_graph = MagicMock(status_code=401, text="expired")
        second_graph = MagicMock(status_code=200, text='{"value": []}')
        second_graph.json.return_value = {"value": []}
        mock_httpx.request.side_effect = [first_graph, second_graph]
        token_response = MagicMock(status_code=200)
        token_response.json.return_value = {
            "access_token": "fresh-access",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = token_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            calendar._access_token = "rejected-access"
            assert calendar._request("GET", "/me/events") == {"value": []}

        assert mock_httpx.request.call_count == 2
        mock_httpx.post.assert_called_once_with(
            "https://oo.openonion.ai/api/v1/oauth/microsoft/refresh",
            headers={"Authorization": "Bearer api-key"},
            json={
                "rejected_access_token_hash": sha256(
                    b"rejected-access"
                ).hexdigest()
            },
        )

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx')
    def test_second_graph_401_is_not_retried(self, mock_httpx):
        """The retry budget is exactly one Graph request."""
        graph_401 = MagicMock(status_code=401, text="expired")
        mock_httpx.request.side_effect = [graph_401, graph_401]
        token_response = MagicMock(status_code=200)
        token_response.json.return_value = {
            "access_token": "fresh-access",
            "expires_in": 3600,
        }
        mock_httpx.post.return_value = token_response

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read,Calendars.ReadWrite",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            calendar = MicrosoftCalendar()
            calendar._access_token = "rejected-access"
            with pytest.raises(ValueError, match="Microsoft Graph API error: 401"):
                calendar._request("GET", "/me/events")

        assert mock_httpx.request.call_count == 2
        assert mock_httpx.post.call_count == 1

    @pytest.mark.token_fetch
    @patch('connectonion.useful_tools.microsoft_calendar.httpx.post')
    def test_token_service_network_failure_is_sanitized(self, post):
        request = httpx.Request("POST", "https://oo.example/refresh")
        post.side_effect = httpx.ConnectError("offline", request=request)

        with patch.dict(os.environ, {
            "MICROSOFT_SCOPES": "Calendars.Read",
            "OPENONION_API_KEY": "api-key",
        }, clear=False):
            from connectonion.useful_tools.microsoft_calendar import MicrosoftCalendar
            with pytest.raises(ValueError, match="token service unavailable"):
                MicrosoftCalendar()._get_access_token()


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
