"""Unit tests for connectonion/useful_tools/google_calendar.py

Tests cover:
- GoogleCalendar initialization with scope validation
- list_events, get_today_events, get_event
- create_event, create_meet, update_event, delete_event
- get_upcoming_meetings, find_free_slots
- _parse_time helper method
- _format_datetime helper method
"""

import pytest
import os
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock


# Future expiry time for tests (1 hour from now)
FUTURE_EXPIRY = (datetime.utcnow() + timedelta(hours=1)).isoformat() + 'Z'


class TestGoogleCalendarInit:
    """Tests for GoogleCalendar initialization and scope validation."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_init_with_valid_scope(self):
        """Test GoogleCalendar initializes successfully with calendar scope."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar()
        assert calendar._service is None  # Lazy loaded

    @patch.dict(os.environ, {"GOOGLE_SCOPES": "gmail.readonly"}, clear=True)
    def test_init_missing_calendar_scope(self):
        """Test GoogleCalendar raises error when calendar scope is missing."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        with pytest.raises(ValueError) as exc_info:
            GoogleCalendar()
        assert "calendar" in str(exc_info.value)
        assert "co auth google" in str(exc_info.value)


class TestGetService:
    """Tests for _get_service method and token handling."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh",
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY
    })
    @patch('connectonion.useful_tools.google_calendar.build')
    def test_get_service_creates_service(self, mock_build):
        """Test _get_service creates Calendar API service."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        mock_service = Mock()
        mock_build.return_value = mock_service

        calendar = GoogleCalendar()
        service = calendar._get_service()

        assert service == mock_service
        mock_build.assert_called_once()

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh",
        "GOOGLE_TOKEN_EXPIRES_AT": FUTURE_EXPIRY
    })
    @patch('connectonion.useful_tools.google_calendar.build')
    def test_get_service_caches_service(self, mock_build):
        """Test _get_service returns cached service on second call."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        mock_service = Mock()
        mock_build.return_value = mock_service

        calendar = GoogleCalendar()
        service1 = calendar._get_service()
        service2 = calendar._get_service()

        assert service1 == service2
        assert mock_build.call_count == 1  # Only built once

    @patch.dict(os.environ, {"GOOGLE_SCOPES": "calendar"}, clear=True)
    def test_get_service_missing_credentials(self):
        """Test _get_service raises error when credentials missing."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar.__new__(GoogleCalendar)
        calendar._service = None

        with pytest.raises(ValueError) as exc_info:
            calendar._get_service()
        assert "Google OAuth credentials not found" in str(exc_info.value)


class TestListEvents:
    """Tests for event listing methods."""

    @pytest.fixture
    def calendar_with_mock(self):
        """Create GoogleCalendar instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "calendar",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.google_calendar import GoogleCalendar
            calendar = GoogleCalendar()
            mock_service = Mock()
            calendar._get_service = Mock(return_value=mock_service)
            return calendar, mock_service

    def test_list_events_basic(self, calendar_with_mock):
        """Test list_events returns formatted event list."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Team Meeting',
                    'start': {'dateTime': '2024-01-15T14:00:00Z'},
                    'end': {'dateTime': '2024-01-15T15:00:00Z'},
                    'attendees': [{'email': 'alice@example.com'}]
                }
            ]
        }

        result = calendar.list_events(days_ahead=7)

        assert "Team Meeting" in result
        assert "alice@example.com" in result

    def test_list_events_with_meet_link(self, calendar_with_mock):
        """Test list_events shows Meet link when available."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Video Call',
                    'start': {'dateTime': '2024-01-15T14:00:00Z'},
                    'end': {'dateTime': '2024-01-15T15:00:00Z'},
                    'hangoutLink': 'https://meet.google.com/abc-defg-hij'
                }
            ]
        }

        result = calendar.list_events()

        assert "meet.google.com" in result

    def test_list_events_empty(self, calendar_with_mock):
        """Test list_events with no events."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {'items': []}

        result = calendar.list_events(days_ahead=7)

        assert "No upcoming events" in result

    def test_get_today_events(self, calendar_with_mock):
        """Test get_today_events returns today's events."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'today1',
                    'summary': 'Morning Standup',
                    'start': {'dateTime': '2024-01-15T09:00:00Z'},
                    'end': {'dateTime': '2024-01-15T09:30:00Z'}
                }
            ]
        }

        result = calendar.get_today_events()

        assert "Today's events" in result
        assert "Morning Standup" in result

    def test_get_today_events_empty(self, calendar_with_mock):
        """Test get_today_events with no events today."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {'items': []}

        result = calendar.get_today_events()

        assert "No events scheduled for today" in result

    def test_get_event_by_id(self, calendar_with_mock):
        """Test get_event returns detailed event info."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().get().execute.return_value = {
            'id': 'event123',
            'summary': 'Project Review',
            'start': {'dateTime': '2024-01-15T14:00:00Z'},
            'end': {'dateTime': '2024-01-15T16:00:00Z'},
            'description': 'Quarterly project review',
            'location': 'Conference Room A',
            'hangoutLink': 'https://meet.google.com/xyz',
            'attendees': [
                {'email': 'alice@example.com', 'responseStatus': 'accepted'},
                {'email': 'bob@example.com', 'responseStatus': 'needsAction'}
            ]
        }

        result = calendar.get_event('event123')

        assert "Project Review" in result
        assert "Quarterly project review" in result
        assert "Conference Room A" in result
        assert "alice@example.com" in result
        assert "accepted" in result


class TestCreateEvents:
    """Tests for event creation methods."""

    @pytest.fixture
    def calendar_with_mock(self):
        """Create GoogleCalendar instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "calendar",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.google_calendar import GoogleCalendar
            calendar = GoogleCalendar()
            mock_service = Mock()
            calendar._get_service = Mock(return_value=mock_service)
            return calendar, mock_service

    def test_create_event_basic(self, calendar_with_mock):
        """Test basic event creation."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().insert().execute.return_value = {
            'id': 'new123',
            'htmlLink': 'https://calendar.google.com/event?id=new123'
        }

        result = calendar.create_event(
            title='New Meeting',
            start_time='2024-01-15 14:00',
            end_time='2024-01-15 15:00'
        )

        assert "Event created" in result
        assert "New Meeting" in result
        assert "new123" in result

    def test_create_event_with_attendees(self, calendar_with_mock):
        """Test event creation with attendees."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().insert().execute.return_value = {
            'id': 'meeting123',
            'htmlLink': 'https://calendar.google.com/event?id=meeting123'
        }

        result = calendar.create_event(
            title='Team Sync',
            start_time='2024-01-15 10:00',
            end_time='2024-01-15 11:00',
            attendees='alice@example.com, bob@example.com',
            location='Room 101'
        )

        assert "Event created" in result
        # Verify attendees were passed
        call_kwargs = mock_service.events().insert.call_args[1]
        event_body = call_kwargs['body']
        assert len(event_body['attendees']) == 2

    def test_create_meet(self, calendar_with_mock):
        """Test Google Meet meeting creation."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().insert().execute.return_value = {
            'id': 'meet123',
            'hangoutLink': 'https://meet.google.com/abc-defg-hij'
        }

        result = calendar.create_meet(
            title='Video Conference',
            start_time='2024-01-15 14:00',
            end_time='2024-01-15 15:00',
            attendees='alice@example.com, bob@example.com'
        )

        assert "Meeting created" in result
        assert "Video Conference" in result
        assert "meet.google.com" in result

        # Verify conferenceData was set
        call_kwargs = mock_service.events().insert.call_args[1]
        assert call_kwargs['conferenceDataVersion'] == 1
        event_body = call_kwargs['body']
        assert 'conferenceData' in event_body


class TestUpdateDeleteEvents:
    """Tests for event update and delete methods."""

    @pytest.fixture
    def calendar_with_mock(self):
        """Create GoogleCalendar instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "calendar",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.google_calendar import GoogleCalendar
            calendar = GoogleCalendar()
            mock_service = Mock()
            calendar._get_service = Mock(return_value=mock_service)
            return calendar, mock_service

    def test_update_event_title(self, calendar_with_mock):
        """Test updating event title."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().get().execute.return_value = {
            'id': 'event123',
            'summary': 'Old Title',
            'start': {'dateTime': '2024-01-15T14:00:00Z'},
            'end': {'dateTime': '2024-01-15T15:00:00Z'}
        }
        mock_service.events().update().execute.return_value = {
            'id': 'event123',
            'summary': 'New Title'
        }

        result = calendar.update_event(event_id='event123', title='New Title')

        assert "Event updated" in result
        assert "New Title" in result

    def test_update_event_time(self, calendar_with_mock):
        """Test updating event time."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().get().execute.return_value = {
            'id': 'event123',
            'summary': 'Meeting',
            'start': {'dateTime': '2024-01-15T14:00:00Z'},
            'end': {'dateTime': '2024-01-15T15:00:00Z'}
        }
        mock_service.events().update().execute.return_value = {
            'id': 'event123',
            'summary': 'Meeting'
        }

        result = calendar.update_event(
            event_id='event123',
            start_time='2024-01-16 10:00',
            end_time='2024-01-16 11:00'
        )

        assert "Event updated" in result

    def test_delete_event(self, calendar_with_mock):
        """Test deleting an event."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().delete().execute.return_value = None

        result = calendar.delete_event('event123')

        assert "Event deleted" in result
        assert "event123" in result
        mock_service.events().delete.assert_called()


class TestMeetings:
    """Tests for meeting-related methods."""

    @pytest.fixture
    def calendar_with_mock(self):
        """Create GoogleCalendar instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "calendar",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.google_calendar import GoogleCalendar
            calendar = GoogleCalendar()
            mock_service = Mock()
            calendar._get_service = Mock(return_value=mock_service)
            return calendar, mock_service

    def test_get_upcoming_meetings(self, calendar_with_mock):
        """Test getting upcoming meetings (events with attendees)."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Solo Task',
                    'start': {'dateTime': '2024-01-15T09:00:00Z'},
                    'end': {'dateTime': '2024-01-15T10:00:00Z'}
                    # No attendees - not a meeting
                },
                {
                    'id': 'event2',
                    'summary': 'Team Meeting',
                    'start': {'dateTime': '2024-01-15T14:00:00Z'},
                    'end': {'dateTime': '2024-01-15T15:00:00Z'},
                    'attendees': [
                        {'email': 'alice@example.com'},
                        {'email': 'bob@example.com'}
                    ],
                    'hangoutLink': 'https://meet.google.com/xyz'
                }
            ]
        }

        result = calendar.get_upcoming_meetings(days_ahead=7)

        assert "Team Meeting" in result
        assert "alice@example.com" in result
        # Solo Task should not appear (no attendees)
        assert "Solo Task" not in result

    def test_get_upcoming_meetings_none(self, calendar_with_mock):
        """Test get_upcoming_meetings with no meetings."""
        calendar, mock_service = calendar_with_mock
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'summary': 'Solo Task',
                    'start': {'dateTime': '2024-01-15T09:00:00Z'},
                    'end': {'dateTime': '2024-01-15T10:00:00Z'}
                }
            ]
        }

        result = calendar.get_upcoming_meetings()

        assert "No upcoming meetings" in result


class TestFreeSlots:
    """Tests for find_free_slots method."""

    @pytest.fixture
    def calendar_with_mock(self):
        """Create GoogleCalendar instance with mocked _get_service."""
        with patch.dict(os.environ, {
            "GOOGLE_SCOPES": "calendar",
            "GOOGLE_ACCESS_TOKEN": "test_token",
            "GOOGLE_REFRESH_TOKEN": "test_refresh"
        }):
            from connectonion.useful_tools.google_calendar import GoogleCalendar
            calendar = GoogleCalendar()
            mock_service = Mock()
            calendar._get_service = Mock(return_value=mock_service)
            return calendar, mock_service

    def test_find_free_slots_basic(self, calendar_with_mock):
        """Test finding free time slots."""
        calendar, mock_service = calendar_with_mock
        # No events - whole day is free
        mock_service.events().list().execute.return_value = {'items': []}

        result = calendar.find_free_slots(date='2024-01-15', duration_minutes=60)

        assert "Free slots" in result
        assert "09:00 AM" in result

    def test_find_free_slots_with_events(self, calendar_with_mock):
        """Test finding free slots around existing events."""
        calendar, mock_service = calendar_with_mock
        # Use ISO format without timezone to avoid offset-aware/naive datetime issues
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'start': {'dateTime': '2024-01-15T10:00:00'},
                    'end': {'dateTime': '2024-01-15T11:00:00'}
                },
                {
                    'id': 'event2',
                    'start': {'dateTime': '2024-01-15T14:00:00'},
                    'end': {'dateTime': '2024-01-15T15:00:00'}
                }
            ]
        }

        result = calendar.find_free_slots(date='2024-01-15', duration_minutes=60)

        assert "Free slots" in result

    def test_find_free_slots_none_available(self, calendar_with_mock):
        """Test find_free_slots when no slots available."""
        calendar, mock_service = calendar_with_mock
        # Full day of back-to-back meetings (no timezone suffix to avoid offset issues)
        mock_service.events().list().execute.return_value = {
            'items': [
                {
                    'id': 'event1',
                    'start': {'dateTime': '2024-01-15T09:00:00'},
                    'end': {'dateTime': '2024-01-15T17:00:00'}
                }
            ]
        }

        result = calendar.find_free_slots(date='2024-01-15', duration_minutes=60)

        assert "No free slots available" in result


class TestParseTime:
    """Tests for _parse_time helper method."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_parse_time_iso_with_z(self):
        """Test parsing ISO format with Z timezone."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar()
        result = calendar._parse_time('2024-01-15T14:00:00Z')
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_parse_time_iso_without_z(self):
        """Test parsing ISO format without timezone."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar()
        result = calendar._parse_time('2024-01-15T14:00:00')
        assert result.year == 2024
        assert result.hour == 14

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_parse_time_simple_format(self):
        """Test parsing simple YYYY-MM-DD HH:MM format."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar()
        result = calendar._parse_time('2024-01-15 14:00')
        assert result.year == 2024
        assert result.month == 1
        assert result.day == 15
        assert result.hour == 14
        assert result.minute == 0

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_parse_time_invalid(self):
        """Test parsing invalid time format raises error."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar()
        with pytest.raises(ValueError) as exc_info:
            calendar._parse_time('invalid-time')
        assert "Cannot parse time" in str(exc_info.value)


class TestFormatDatetime:
    """Tests for _format_datetime helper method."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_format_datetime_iso(self):
        """Test formatting ISO datetime to readable format."""
        from connectonion.useful_tools.google_calendar import GoogleCalendar
        calendar = GoogleCalendar()
        result = calendar._format_datetime('2024-01-15T14:30:00Z')
        assert '2024-01-15' in result
        assert '02:30 PM' in result


class TestGoogleCalendarIntegration:
    """Integration tests for GoogleCalendar as agent tool."""

    @patch.dict(os.environ, {
        "GOOGLE_SCOPES": "calendar",
        "GOOGLE_ACCESS_TOKEN": "test_token",
        "GOOGLE_REFRESH_TOKEN": "test_refresh"
    })
    def test_google_calendar_integrates_with_agent(self):
        """Test that GoogleCalendar can be used as an agent tool."""
        from connectonion import Agent
        from connectonion.llm import LLMResponse
        from connectonion.usage import TokenUsage
        from connectonion.useful_tools.google_calendar import GoogleCalendar

        # Create mock LLM
        mock_llm = Mock()
        mock_llm.complete.return_value = LLMResponse(
            content="Test response",
            tool_calls=[],
            raw_response=None,
            usage=TokenUsage(),
        )

        calendar = GoogleCalendar()

        # Should not raise
        agent = Agent(
            "test",
            llm=mock_llm,
            tools=[calendar],
            log=False,
        )

        # Verify GoogleCalendar methods are registered as tools
        assert 'list_events' in agent.tools
        assert 'get_today_events' in agent.tools
        assert 'get_event' in agent.tools
        assert 'create_event' in agent.tools
        assert 'create_meet' in agent.tools
        assert 'update_event' in agent.tools
        assert 'delete_event' in agent.tools
        assert 'get_upcoming_meetings' in agent.tools
        assert 'find_free_slots' in agent.tools
