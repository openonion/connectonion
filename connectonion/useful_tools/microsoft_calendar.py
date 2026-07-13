"""
Purpose: Microsoft Calendar integration tool for managing events via Microsoft Graph API
LLM-Note:
  Dependencies: imports from [os, datetime, httpx] | imported by [useful_tools/__init__.py] | requires 'co auth' + 'co auth microsoft' | tested by [tests/unit/test_microsoft_calendar.py]
  Data flow: Agent calls MicrosoftCalendar methods → _get_access_token() asks oo-api for a usable short-lived token → HTTP calls to Graph API (https://graph.microsoft.com/v1.0) → returns formatted results (event lists, confirmations, free slots)
  State/Effects: keeps one access token in instance memory | makes HTTP calls to oo-api and Microsoft Graph API | can create/update/delete events, create Teams meetings | no local token persistence
  Integration: exposes MicrosoftCalendar class with list_events(), get_today_events(), get_event(), create_event(), update_event(), delete_event(), create_teams_meeting(), get_upcoming_meetings(), find_free_slots(), check_availability() | used as agent tool via Agent(tools=[MicrosoftCalendar()])
  Performance: network I/O per API call | batch fetching for list operations | date parsing for queries
  Errors: raises ValueError if OAuth not configured | HTTP errors from Graph API propagate | returns error strings for display

Microsoft Calendar tool for managing calendar events via Microsoft Graph API.

Usage:
    from connectonion import Agent, MicrosoftCalendar

    calendar = MicrosoftCalendar()
    agent = Agent("assistant", tools=[calendar])

    # Agent can now use:
    # - list_events(days_ahead, max_results)
    # - get_today_events()
    # - get_event(event_id)
    # - create_event(title, start_time, end_time, description, attendees, location)
    # - update_event(event_id, title, start_time, end_time, description, attendees, location)
    # - delete_event(event_id)
    # - create_teams_meeting(title, start_time, end_time, attendees, description)
    # - get_upcoming_meetings(days_ahead)
    # - find_free_slots(date, duration_minutes)
    # - check_availability(datetime_str)

Example:
    from connectonion import Agent, MicrosoftCalendar

    calendar = MicrosoftCalendar()
    agent = Agent(
        name="calendar-assistant",
        system_prompt="You are a calendar assistant.",
        tools=[calendar]
    )

    agent.input("What meetings do I have today?")
    agent.input("Schedule a meeting with alice@example.com tomorrow at 2pm")
"""

import os
from datetime import datetime, timedelta
from hashlib import sha256
import time
from typing import Optional
import httpx
from httpx import RequestError


class MicrosoftCalendar:
    """Microsoft Calendar tool for managing events via Microsoft Graph API."""

    GRAPH_API_URL = "https://graph.microsoft.com/v1.0"
    ACCESS_TOKEN_REFRESH_BUFFER_SECONDS = 5 * 60
    MAX_ACCESS_TOKEN_LIFETIME_SECONDS = 24 * 60 * 60

    def __init__(self):
        """Initialize Microsoft Calendar tool.

        Validates that Microsoft OAuth is configured with Calendar scopes.
        Raises ValueError if credentials are missing.
        """
        scopes = os.getenv("MICROSOFT_SCOPES", "")
        if not scopes or "Calendars" not in scopes:
            raise ValueError(
                "Missing Microsoft Calendar scopes.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Microsoft Calendar access:\n"
                "  co auth microsoft"
            )

        self._access_token = None
        self._access_token_refresh_at = None

    def _get_access_token(self) -> str:
        """Return the instance token, asking oo-api on first use."""
        if (
            not self._access_token
            or (
                self._access_token_refresh_at is not None
                and time.monotonic() >= self._access_token_refresh_at
            )
        ):
            self._access_token = self._fetch_access_token()
        return self._access_token

    def _fetch_access_token(
        self,
        rejected_access_token: Optional[str] = None,
    ) -> str:
        """Ask oo-api for a usable access token; refresh tokens stay server-side."""
        backend_url = os.getenv(
            "OPENONION_API_URL", "https://oo.openonion.ai"
        ).rstrip("/")
        api_key = os.getenv("OPENONION_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENONION_API_KEY not found.\n"
                "Authenticate with OpenOnion first: co auth"
            )

        request = {
            "headers": {"Authorization": f"Bearer {api_key}"},
        }
        if rejected_access_token:
            request["json"] = {
                "rejected_access_token_hash": sha256(
                    rejected_access_token.encode()
                ).hexdigest()
            }
        try:
            response = httpx.post(
                f"{backend_url}/api/v1/oauth/microsoft/refresh", **request
            )
        except RequestError as exc:
            raise ValueError(
                "Microsoft token service unavailable. Please try again."
            ) from exc

        if response.status_code in {404, 409}:
            raise ValueError(
                "Microsoft authorization expired.\n"
                "Reconnect with: co auth microsoft"
            )
        if response.status_code in {401, 403}:
            raise ValueError("OpenOnion authentication expired.\nRun: co auth")
        if response.status_code != 200:
            raise ValueError(
                f"Microsoft token service unavailable ({response.status_code}). "
                "Please try again."
            )

        try:
            payload = response.json()
            access_token = payload["access_token"]
            expires_in = payload["expires_in"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ValueError("oo-api returned an invalid Microsoft token response") from exc
        if (
            not isinstance(access_token, str)
            or not access_token
            or isinstance(expires_in, bool)
            or not isinstance(expires_in, int)
            or expires_in <= 0
            or expires_in > self.MAX_ACCESS_TOKEN_LIFETIME_SECONDS
        ):
            raise ValueError("oo-api returned an invalid Microsoft token response")
        self._access_token_refresh_at = time.monotonic() + max(
            0,
            expires_in - self.ACCESS_TOKEN_REFRESH_BUFFER_SECONDS,
        )
        return access_token

    def _request(self, method: str, endpoint: str, **kwargs) -> dict:
        """Make authenticated request to Microsoft Graph API."""
        token = self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json"
        }

        url = f"{self.GRAPH_API_URL}{endpoint}"
        response = httpx.request(method, url, headers=headers, **kwargs)

        if response.status_code == 401:
            self._access_token = None
            self._access_token_refresh_at = None
            token = self._fetch_access_token(rejected_access_token=token)
            self._access_token = token
            headers["Authorization"] = f"Bearer {token}"
            response = httpx.request(method, url, headers=headers, **kwargs)

        if response.status_code not in [200, 201, 202, 204]:
            raise ValueError(f"Microsoft Graph API error: {response.status_code} - {response.text}")

        if response.status_code == 204:
            return {}
        return response.json()

    def _format_datetime(self, dt_str: str) -> str:
        """Format datetime string to readable format."""
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %I:%M %p')

    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string to datetime object."""
        for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M']:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Cannot parse time: {time_str}. Use format: YYYY-MM-DD HH:MM or ISO format")

    # === Reading Events ===

    def list_events(self, days_ahead: int = 7, max_results: int = 20) -> str:
        """List upcoming calendar events.

        Args:
            days_ahead: Number of days to look ahead (default: 7)
            max_results: Maximum number of events to return (default: 20)

        Returns:
            Formatted string with event list
        """
        now = datetime.utcnow()
        end = now + timedelta(days=days_ahead)

        endpoint = "/me/calendar/calendarView"
        params = {
            "startDateTime": now.isoformat() + 'Z',
            "endDateTime": end.isoformat() + 'Z',
            "$top": max_results,
            "$orderby": "start/dateTime",
            "$select": "id,subject,start,end,attendees,onlineMeeting,onlineMeetingUrl"
        }

        result = self._request("GET", endpoint, params=params)
        events = result.get('value', [])

        if not events:
            return f"No upcoming events in the next {days_ahead} days."

        output = [f"Upcoming events (next {days_ahead} days):\n"]
        for event in events:
            start = event.get('start', {}).get('dateTime', '')
            subject = event.get('subject', 'No title')
            event_id = event['id']

            attendees = event.get('attendees', [])
            attendee_str = ""
            if attendees:
                attendee_emails = [a.get('emailAddress', {}).get('address', '') for a in attendees]
                if attendee_emails:
                    attendee_str = f"\n   Attendees: {', '.join(attendee_emails)}"

            meeting_url = event.get('onlineMeetingUrl', '')
            meeting_str = f"\n   Meeting: {meeting_url}" if meeting_url else ""

            output.append(f"- {self._format_datetime(start)}: {subject}")
            output.append(f"   ID: {event_id}{attendee_str}{meeting_str}\n")

        return "\n".join(output)

    def get_today_events(self) -> str:
        """Get today's calendar events.

        Returns:
            Formatted string with today's events
        """
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999)

        endpoint = "/me/calendar/calendarView"
        params = {
            "startDateTime": start_of_day.isoformat() + 'Z',
            "endDateTime": end_of_day.isoformat() + 'Z',
            "$orderby": "start/dateTime",
            "$select": "id,subject,start,end,onlineMeetingUrl"
        }

        result = self._request("GET", endpoint, params=params)
        events = result.get('value', [])

        if not events:
            return "No events scheduled for today."

        output = ["Today's events:\n"]
        for event in events:
            start = event.get('start', {}).get('dateTime', '')
            subject = event.get('subject', 'No title')
            meeting_url = event.get('onlineMeetingUrl', '')
            meeting_str = f" [Meeting: {meeting_url}]" if meeting_url else ""

            output.append(f"- {self._format_datetime(start)}: {subject}{meeting_str}")

        return "\n".join(output)

    def get_event(self, event_id: str) -> str:
        """Get detailed information about a specific event.

        Args:
            event_id: Calendar event ID

        Returns:
            Formatted event details
        """
        endpoint = f"/me/calendar/events/{event_id}"
        params = {
            "$select": "subject,start,end,body,location,attendees,onlineMeetingUrl"
        }

        event = self._request("GET", endpoint, params=params)

        subject = event.get('subject', 'No title')
        start = event.get('start', {}).get('dateTime', '')
        end = event.get('end', {}).get('dateTime', '')
        body = event.get('body', {}).get('content', 'No description')
        location = event.get('location', {}).get('displayName', 'No location')

        attendees = event.get('attendees', [])
        attendee_list = []
        for a in attendees:
            email = a.get('emailAddress', {}).get('address', '')
            status = a.get('status', {}).get('response', 'none')
            attendee_list.append(f"{email} ({status})")

        meeting_url = event.get('onlineMeetingUrl', 'No meeting link')

        output = [
            f"Event: {subject}",
            f"Start: {self._format_datetime(start)}",
            f"End: {self._format_datetime(end)}",
            f"Location: {location}",
            f"Meeting: {meeting_url}",
        ]

        if attendee_list:
            output.append(f"Attendees:\n  " + "\n  ".join(attendee_list))

        return "\n".join(output)

    # === Creating Events ===

    def create_event(self, title: str, start_time: str, end_time: str,
                     description: str = None, attendees: str = None,
                     location: str = None) -> str:
        """Create a new calendar event.

        Args:
            title: Event title
            start_time: Start time (ISO format or "YYYY-MM-DD HH:MM")
            end_time: End time (ISO format or "YYYY-MM-DD HH:MM")
            description: Optional event description
            attendees: Optional comma-separated email addresses
            location: Optional location

        Returns:
            Confirmation with event ID and details
        """
        start_dt = self._parse_time(start_time)
        end_dt = self._parse_time(end_time)

        event = {
            "subject": title,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "UTC"
            }
        }

        if description:
            event["body"] = {
                "contentType": "Text",
                "content": description
            }

        if location:
            event["location"] = {"displayName": location}

        if attendees:
            event["attendees"] = [
                {
                    "emailAddress": {"address": email.strip()},
                    "type": "required"
                }
                for email in attendees.split(',')
            ]

        created_event = self._request("POST", "/me/calendar/events", json=event)

        return f"Event created: {title}\nStart: {self._format_datetime(start_dt.isoformat())}\nEvent ID: {created_event['id']}\nLink: {created_event.get('webLink', '')}"

    def create_teams_meeting(self, title: str, start_time: str, end_time: str,
                             attendees: str, description: str = None) -> str:
        """Create a Microsoft Teams meeting.

        Args:
            title: Meeting title
            start_time: Start time (ISO format or "YYYY-MM-DD HH:MM")
            end_time: End time (ISO format or "YYYY-MM-DD HH:MM")
            attendees: Comma-separated email addresses
            description: Optional meeting description

        Returns:
            Confirmation with Teams meeting link
        """
        start_dt = self._parse_time(start_time)
        end_dt = self._parse_time(end_time)

        event = {
            "subject": title,
            "start": {
                "dateTime": start_dt.isoformat(),
                "timeZone": "UTC"
            },
            "end": {
                "dateTime": end_dt.isoformat(),
                "timeZone": "UTC"
            },
            "attendees": [
                {
                    "emailAddress": {"address": email.strip()},
                    "type": "required"
                }
                for email in attendees.split(',')
            ],
            "isOnlineMeeting": True,
            "onlineMeetingProvider": "teamsForBusiness"
        }

        if description:
            event["body"] = {
                "contentType": "Text",
                "content": description
            }

        created_event = self._request("POST", "/me/calendar/events", json=event)

        meeting_url = created_event.get('onlineMeeting', {}).get('joinUrl', '') or created_event.get('onlineMeetingUrl', 'No meeting link')

        return f"Teams meeting created: {title}\nStart: {self._format_datetime(start_dt.isoformat())}\nTeams link: {meeting_url}\nEvent ID: {created_event['id']}"

    def update_event(self, event_id: str, title: str = None, start_time: str = None,
                     end_time: str = None, description: str = None,
                     attendees: str = None, location: str = None) -> str:
        """Update an existing calendar event.

        Args:
            event_id: Calendar event ID
            title: Optional new title
            start_time: Optional new start time
            end_time: Optional new end time
            description: Optional new description
            attendees: Optional new comma-separated attendees
            location: Optional new location

        Returns:
            Confirmation message
        """
        updates = {}

        if title:
            updates["subject"] = title
        if description:
            updates["body"] = {"contentType": "Text", "content": description}
        if location:
            updates["location"] = {"displayName": location}
        if start_time:
            start_dt = self._parse_time(start_time)
            updates["start"] = {"dateTime": start_dt.isoformat(), "timeZone": "UTC"}
        if end_time:
            end_dt = self._parse_time(end_time)
            updates["end"] = {"dateTime": end_dt.isoformat(), "timeZone": "UTC"}
        if attendees:
            updates["attendees"] = [
                {"emailAddress": {"address": email.strip()}, "type": "required"}
                for email in attendees.split(',')
            ]

        endpoint = f"/me/calendar/events/{event_id}"
        updated_event = self._request("PATCH", endpoint, json=updates)

        return f"Event updated: {updated_event.get('subject', 'Unknown')}\nEvent ID: {event_id}"

    def delete_event(self, event_id: str) -> str:
        """Delete a calendar event.

        Args:
            event_id: Calendar event ID

        Returns:
            Confirmation message
        """
        endpoint = f"/me/calendar/events/{event_id}"
        self._request("DELETE", endpoint)

        return f"Event deleted: {event_id}"

    # === Meeting Management ===

    def get_upcoming_meetings(self, days_ahead: int = 7) -> str:
        """Get upcoming meetings (events with attendees).

        Args:
            days_ahead: Number of days to look ahead (default: 7)

        Returns:
            Formatted list of upcoming meetings
        """
        now = datetime.utcnow()
        end = now + timedelta(days=days_ahead)

        endpoint = "/me/calendar/calendarView"
        params = {
            "startDateTime": now.isoformat() + 'Z',
            "endDateTime": end.isoformat() + 'Z',
            "$orderby": "start/dateTime",
            "$select": "id,subject,start,attendees,onlineMeetingUrl"
        }

        result = self._request("GET", endpoint, params=params)
        events = result.get('value', [])

        meetings = [e for e in events if e.get('attendees')]

        if not meetings:
            return f"No upcoming meetings in the next {days_ahead} days."

        output = [f"Upcoming meetings (next {days_ahead} days):\n"]
        for meeting in meetings:
            start = meeting.get('start', {}).get('dateTime', '')
            subject = meeting.get('subject', 'No title')
            attendees = meeting.get('attendees', [])
            attendee_emails = [a.get('emailAddress', {}).get('address', '') for a in attendees]
            meeting_url = meeting.get('onlineMeetingUrl', '')

            output.append(f"- {self._format_datetime(start)}: {subject}")
            output.append(f"   Attendees: {', '.join(attendee_emails)}")
            if meeting_url:
                output.append(f"   Meeting: {meeting_url}")
            output.append("")

        return "\n".join(output)

    def find_free_slots(self, date: str, duration_minutes: int = 60) -> str:
        """Find free time slots on a specific date.

        Args:
            date: Date to check (YYYY-MM-DD format)
            duration_minutes: Desired meeting duration (default: 60)

        Returns:
            List of available time slots
        """
        target_date = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = target_date.replace(hour=9, minute=0, second=0)
        end_of_day = target_date.replace(hour=17, minute=0, second=0)

        endpoint = "/me/calendar/calendarView"
        params = {
            "startDateTime": start_of_day.isoformat() + 'Z',
            "endDateTime": end_of_day.isoformat() + 'Z',
            "$orderby": "start/dateTime",
            "$select": "start,end"
        }

        result = self._request("GET", endpoint, params=params)
        events = result.get('value', [])

        free_slots = []
        current_time = start_of_day

        for event in events:
            event_start_str = event.get('start', {}).get('dateTime', '')
            event_end_str = event.get('end', {}).get('dateTime', '')

            if not event_start_str or not event_end_str:
                continue

            event_start = datetime.fromisoformat(event_start_str.replace('Z', '+00:00')).replace(tzinfo=None)
            event_end = datetime.fromisoformat(event_end_str.replace('Z', '+00:00')).replace(tzinfo=None)

            if (event_start - current_time).total_seconds() >= duration_minutes * 60:
                free_slots.append(f"{current_time.strftime('%I:%M %p')} - {event_start.strftime('%I:%M %p')}")

            current_time = max(current_time, event_end)

        if (end_of_day - current_time).total_seconds() >= duration_minutes * 60:
            free_slots.append(f"{current_time.strftime('%I:%M %p')} - {end_of_day.strftime('%I:%M %p')}")

        if not free_slots:
            return f"No free slots available on {date} for {duration_minutes} minute meetings."

        return f"Free slots on {date} ({duration_minutes}+ minutes):\n" + "\n".join(f"  - {slot}" for slot in free_slots)

    def check_availability(self, datetime_str: str) -> str:
        """Check if a specific time is free.

        Args:
            datetime_str: DateTime to check (ISO format or "YYYY-MM-DD HH:MM")

        Returns:
            Whether the time slot is available
        """
        target_time = self._parse_time(datetime_str)
        check_end = target_time + timedelta(hours=1)

        endpoint = "/me/calendar/calendarView"
        params = {
            "startDateTime": target_time.isoformat() + 'Z',
            "endDateTime": check_end.isoformat() + 'Z',
            "$select": "subject,start,end"
        }

        result = self._request("GET", endpoint, params=params)
        events = result.get('value', [])

        if not events:
            return f"Time slot {self._format_datetime(target_time.isoformat())} is FREE"

        conflicts = []
        for event in events:
            subject = event.get('subject', 'Untitled')
            start = event.get('start', {}).get('dateTime', '')
            conflicts.append(f"- {subject} at {self._format_datetime(start)}")

        return f"Time slot {self._format_datetime(target_time.isoformat())} is BUSY:\n" + "\n".join(conflicts)
