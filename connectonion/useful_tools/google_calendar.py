"""
Purpose: Google Calendar integration tool for managing events and meetings via Google API
LLM-Note:
  Dependencies: imports from [os, datetime, google.oauth2.credentials, googleapiclient.discovery] | imported by [useful_tools/__init__.py] | requires OAuth tokens from 'co auth google' | tested by [tests/unit/test_google_calendar.py]
  Data flow: Agent calls GoogleCalendar methods → refreshes the locally held Google token through oo-api's stateless exchange → builds Calendar API service → direct calls to Calendar REST endpoints → returns formatted results (event lists, confirmations, free slots)
  State/Effects: reads GOOGLE_* env vars and OPENONION_API_KEY | persists refreshed tokens only to the selected record (process overrides remain in memory) | makes HTTP calls to Google Calendar API | can create/update/delete events
  Integration: exposes GoogleCalendar class with list_events(), get_today_events(), get_event(), create_event(), update_event(), delete_event(), create_meet(), get_upcoming_meetings(), find_free_slots() | used as agent tool via Agent(tools=[GoogleCalendar()])
  Performance: network I/O per API call | batch fetching for list operations | date parsing for queries
  Errors: raises ValueError if OAuth not configured | Google API errors propagate | returns error strings for display

Google Calendar tool for managing calendar events and meetings.

Usage:
    from connectonion import Agent, GoogleCalendar

    calendar = GoogleCalendar()
    agent = Agent("assistant", tools=[calendar])

    # Agent can now use:
    # - list_events(days_ahead, max_results)
    # - get_today_events()
    # - get_event(event_id)
    # - create_event(title, start_time, end_time, description, attendees, location)
    # - update_event(event_id, title, start_time, end_time, description, attendees, location)
    # - delete_event(event_id)
    # - create_meet(title, start_time, end_time, attendees, description)
    # - get_upcoming_meetings(days_ahead)
    # - find_free_slots(date, duration_minutes)

Example:
    from connectonion import Agent, GoogleCalendar

    calendar = GoogleCalendar()
    agent = Agent(
        name="calendar-assistant",
        system_prompt="You are a calendar assistant.",
        tools=[calendar]
    )

    agent.input("What meetings do I have today?")
    agent.input("Schedule a meeting with aaron@openonion.ai tomorrow at 2pm")
"""

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from ..backend import backend_url
from ..credentials import require_ambient_api_key
from ..provider_credentials import resolve_provider_credentials, refresh_credentials, token_expiry


def _addresses(attendees) -> list:
    """The comma-separated list as clean addresses, empty when there are none."""
    if not attendees:
        return []
    return [email.strip() for email in attendees.split(',') if email.strip()]


def _send_updates(invited) -> str:
    """Google defaults this to 'none', which is why invitations reached nobody.

    'all' whenever there is somebody to tell. 'none' for a solo event, because
    asking Google to mail an empty list is a pointless round trip and it makes
    "who was notified" unanswerable by always being "everyone".
    """
    return 'all' if invited else 'none'


def _kept_attendees(existing, attendees) -> list:
    """The new attendee list, carrying over what Google already knows.

    The list of addresses is authoritative for *who* is on the event. What it
    must not decide is what those people already said.

    Rebuilding every entry as a bare `{'email': …}` dropped `responseStatus`,
    and Google reads its absence as `needsAction` — so adding one person
    un-answered everybody. Since `sendUpdates='all'` (#1548) that also emails a
    fresh invitation to people who had already accepted, which is the version
    anyone notices. The whole entry is reused, not just the status: `organizer`,
    `optional`, `comment` and `displayName` live on it too.

    Addresses are matched case-insensitively, because a mail system considers
    Aaron@Example.com and aaron@example.com the same person and re-typing the
    address with different capitals must not reset them.
    """
    known = {}
    for entry in existing or []:
        email = (entry.get('email') or '').strip().lower()
        if email:
            known[email] = entry

    result = []
    for email in _addresses(attendees):
        entry = known.get(email.lower())
        # The address as typed this time, so a corrected display form sticks;
        # everything else Google told us about them is carried over.
        result.append({**entry, 'email': email} if entry else {'email': email})
    return result


def _invited_line(invited) -> str:
    """Who was told, so the operator can check it from the output.

    "Event created" read identically whether three people were invited or
    nobody was, so a silent failure looked exactly like a success — which is
    how this went unnoticed until an attendee said they got nothing.
    """
    if not invited:
        return ""
    return f"Invitations sent: {', '.join(invited)}\n"


class GoogleCalendar:
    """Google Calendar tool for managing events and meetings."""

    @property
    def _credentials(self):
        if not hasattr(self, "_credential_record"):
            self._credential_record = resolve_provider_credentials("google")
        return self._credential_record

    @_credentials.setter
    def _credentials(self, value):
        self._credential_record = value

    def __init__(self):
        """Initialize Google Calendar tool.

        Validates that calendar scope is authorized.
        Raises ValueError if scope is missing.
        """
        from .google_scopes import granted_scopes
        self._credentials = resolve_provider_credentials("google")
        scopes = self._credentials.scopes
        if not scopes:
            self._credentials.require_configured()
        if scopes and not scopes.intersection({"calendar", "calendar.readonly"}):
            raise ValueError(
                "Missing 'calendar' scope.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Google Calendar access:\n"
                "  co auth google"
            )

        self._service = None

    def _get_service(self):
        """Build a Calendar service using credentials held on this computer."""
        if self._service:
            return self._service

        self._credentials.require_configured()
        access_token = self._credentials.get("ACCESS_TOKEN")
        expiry = token_expiry(self._credentials.get("TOKEN_EXPIRES_AT"))
        if self._credentials.get("REFRESH_TOKEN") or not access_token or (expiry and expiry <= datetime.now(timezone.utc) + timedelta(minutes=5)):
            access_token = self._refresh_via_backend(None)
        creds = Credentials(
            token=access_token,
            refresh_token=None,
            scopes=self._credentials.scopes or None,
            expiry=self._token_expiry(),
            refresh_handler=self._refresh_handler,
        )

        self._service = build('calendar', 'v3', credentials=creds)
        return self._service

    def _token_expiry(self) -> datetime | None:
        expiry = token_expiry(self._credentials.get("TOKEN_EXPIRES_AT"))
        return expiry.replace(tzinfo=None) if expiry else None

    def _refresh_handler(self, request, scopes=None):
        """Recover a long-running cached Calendar service after a 401."""
        return self._refresh_via_backend(None), self._token_expiry()

    def _refresh_via_backend(self, refresh_token: str | None) -> str:
        # The argument is retained for callers; it must belong to this record.
        from ..provider_credentials import ProviderCredentialError
        api_key = require_ambient_api_key()
        if refresh_token and refresh_token != self._credentials.get("REFRESH_TOKEN"):
            raise ProviderCredentialError("record_changed", "Refresh token differs from the selected account.", "co status")
        return refresh_credentials(self._credentials, backend=backend_url(),
                                   api_key=api_key)

    def _confirmed_time(self, typed: str, converted: datetime) -> str:
        """The time as the caller wrote it, when they said which zone they meant.

        `_parse_time` converts to UTC and drops the offset, so confirming the
        converted value answered "16:30 in Sydney?" with "06:30 AM UTC". True,
        unambiguous since the zone is labelled — and still a subtraction the
        reader has to do to check their own meeting.

        So when the input carried an offset, confirm in that offset: the line
        can then be compared with what was typed, character for character,
        which is the whole job of a confirmation. A naive input has no zone to
        preserve and falls back to the converted value, labelled UTC.
        """
        try:
            original = datetime.fromisoformat(str(typed).replace('Z', '+00:00'))
        except (TypeError, ValueError):
            return self._format_datetime(converted.isoformat())
        if original.tzinfo is None:
            return self._format_datetime(converted.isoformat())
        return self._format_datetime(original.isoformat())

    def _format_datetime(self, dt_str: str) -> str:
        """A readable time that says which zone it is in.

        Without the zone this sentence is a trap. `_parse_time` converts an
        offset to UTC, so a meeting entered as 16:30+10:00 was confirmed as
        "2026-09-15 06:30 AM" — the right instant, described in a way no reader
        interprets correctly. The event was fine; the sentence about it was not.

        A value carrying its own offset keeps it, because relabelling that as
        UTC would be the same bug pointed the other way.
        """
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        shown = dt.strftime('%Y-%m-%d %I:%M %p')
        if dt.tzinfo is None:
            # Naive here always means UTC: it is what _parse_time produces and
            # what the event body is labelled with.
            return f"{shown} UTC"
        if dt.utcoffset() == timedelta(0):
            return f"{shown} UTC"
        return f"{shown} {dt.strftime('%z')[:3]}:{dt.strftime('%z')[3:]}"

    # === Reading Events ===

    def list_events(self, days_ahead: int = 7, max_results: int = 20) -> str:
        """List upcoming calendar events.

        Args:
            days_ahead: Number of days to look ahead (default: 7)
            max_results: Maximum number of events to return (default: 20)

        Returns:
            Formatted string with event list
        """
        service = self._get_service()

        now = datetime.utcnow().isoformat() + 'Z'
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=end,
            maxResults=max_results,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return f"No upcoming events in the next {days_ahead} days."

        output = [f"Upcoming events (next {days_ahead} days):\n"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')
            event_id = event['id']

            # Get attendees if any
            attendees = event.get('attendees', [])
            attendee_str = ""
            if attendees:
                attendee_emails = [a.get('email', '') for a in attendees if a.get('email')]
                if attendee_emails:
                    attendee_str = f"\n   Attendees: {', '.join(attendee_emails)}"

            # Get meet link if any
            meet_link = event.get('hangoutLink', '')
            meet_str = f"\n   Meet: {meet_link}" if meet_link else ""

            output.append(f"- {self._format_datetime(start)}: {summary}")
            output.append(f"   ID: {event_id}{attendee_str}{meet_str}\n")

        return "\n".join(output)

    def get_today_events(self) -> str:
        """Get today's calendar events.

        Returns:
            Formatted string with today's events
        """
        service = self._get_service()

        # Get start and end of today
        now = datetime.utcnow()
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat() + 'Z'
        end_of_day = now.replace(hour=23, minute=59, second=59, microsecond=999999).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        if not events:
            return "No events scheduled for today."

        output = ["Today's events:\n"]
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            summary = event.get('summary', 'No title')

            # Get meet link if any
            meet_link = event.get('hangoutLink', '')
            meet_str = f" [Meet: {meet_link}]" if meet_link else ""

            output.append(f"- {self._format_datetime(start)}: {summary}{meet_str}")

        return "\n".join(output)

    def get_event(self, event_id: str) -> str:
        """Get detailed information about a specific event.

        Args:
            event_id: Calendar event ID

        Returns:
            Formatted event details
        """
        service = self._get_service()

        event = service.events().get(
            calendarId='primary',
            eventId=event_id
        ).execute()

        summary = event.get('summary', 'No title')
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        description = event.get('description', 'No description')
        location = event.get('location', 'No location')

        attendees = event.get('attendees', [])
        attendee_list = []
        for a in attendees:
            email = a.get('email', '')
            status = a.get('responseStatus', 'needsAction')
            attendee_list.append(f"{email} ({status})")

        meet_link = event.get('hangoutLink', 'No Meet link')

        output = [
            f"Event: {summary}",
            f"Start: {self._format_datetime(start)}",
            f"End: {self._format_datetime(end)}",
            f"Description: {description}",
            f"Location: {location}",
            f"Meet: {meet_link}",
        ]

        if attendee_list:
            output.append("Attendees:\n  " + "\n  ".join(attendee_list))

        return "\n".join(output)

    # === Creating Events ===

    def create_event(self, title: str, start_time: str, end_time: str,
                     description: str = None, attendees: str = None,
                     location: str = None) -> str:
        """Create a new calendar event.

        Args:
            title: Event title
            start_time: Start time (ISO format or natural like "2024-01-15 14:00")
            end_time: End time (ISO format or natural like "2024-01-15 15:00")
            description: Optional event description
            attendees: Optional comma-separated email addresses
            location: Optional location

        Returns:
            Confirmation with event ID and details
        """
        service = self._get_service()

        # Parse times
        start_dt = self._parse_time(start_time)
        end_dt = self._parse_time(end_time)

        event = {
            'summary': title,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'UTC',
            },
        }

        if description:
            event['description'] = description

        if location:
            event['location'] = location

        invited = _addresses(attendees)
        if invited:
            event['attendees'] = [{'email': email} for email in invited]

        created_event = service.events().insert(
            calendarId='primary',
            body=event,
            sendUpdates=_send_updates(invited),
        ).execute()

        return (f"Event created: {title}\n"
                f"Start: {self._confirmed_time(start_time, start_dt)}\n"
                f"{_invited_line(invited)}"
                f"Event ID: {created_event['id']}\n"
                f"Link: {created_event.get('htmlLink', '')}")

    def create_meet(self, title: str, start_time: str, end_time: str,
                    attendees: str, description: str = None) -> str:
        """Create a Google Meet meeting.

        Args:
            title: Meeting title
            start_time: Start time (ISO format or natural)
            end_time: End time (ISO format or natural)
            attendees: Comma-separated email addresses
            description: Optional meeting description

        Returns:
            Confirmation with Meet link
        """
        service = self._get_service()

        # Parse times
        start_dt = self._parse_time(start_time)
        end_dt = self._parse_time(end_time)

        attendee_list = [{'email': email} for email in _addresses(attendees)]

        event = {
            'summary': title,
            'start': {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'UTC',
            },
            'end': {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'UTC',
            },
            'attendees': attendee_list,
            'conferenceData': {
                'createRequest': {
                    'requestId': f"meet-{datetime.utcnow().timestamp()}",
                    'conferenceSolutionKey': {'type': 'hangoutsMeet'}
                }
            }
        }

        if description:
            event['description'] = description

        created_event = service.events().insert(
            calendarId='primary',
            body=event,
            conferenceDataVersion=1,
            sendUpdates=_send_updates(attendee_list),
        ).execute()

        meet_link = created_event.get('hangoutLink', 'No Meet link generated')

        return (f"Meeting created: {title}\n"
                f"Start: {self._confirmed_time(start_time, start_dt)}\n"
                f"Meet link: {meet_link}\n"
                f"{_invited_line([a['email'] for a in attendee_list])}"
                f"Event ID: {created_event['id']}")

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
        service = self._get_service()

        # Get existing event
        event = service.events().get(
            calendarId='primary',
            eventId=event_id
        ).execute()

        # Update fields
        if title:
            event['summary'] = title
        if description:
            event['description'] = description
        if location:
            event['location'] = location
        if start_time:
            start_dt = self._parse_time(start_time)
            event['start'] = {
                'dateTime': start_dt.isoformat(),
                'timeZone': 'UTC',
            }
        if end_time:
            end_dt = self._parse_time(end_time)
            event['end'] = {
                'dateTime': end_dt.isoformat(),
                'timeZone': 'UTC',
            }
        if attendees:
            event['attendees'] = _kept_attendees(event.get('attendees'), attendees)

        # 'all' unconditionally, unlike create: the people to tell are the ones
        # already on the event, and this call does not know who they are. An
        # attendee who is never told a meeting moved is worse off than one who
        # was never invited — they hold the old slot and arrive at nothing.
        updated_event = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event,
            sendUpdates='all',
        ).execute()

        return f"Event updated: {updated_event['summary']}\nEvent ID: {event_id}"

    def delete_event(self, event_id: str) -> str:
        """Delete a calendar event.

        Args:
            event_id: Calendar event ID

        Returns:
            Confirmation message
        """
        service = self._get_service()

        service.events().delete(
            calendarId='primary',
            eventId=event_id,
            sendUpdates='all',
        ).execute()

        return f"Event deleted: {event_id}"

    # === Meeting Management ===

    def get_upcoming_meetings(self, days_ahead: int = 7) -> str:
        """Get upcoming meetings (events with attendees).

        Args:
            days_ahead: Number of days to look ahead (default: 7)

        Returns:
            Formatted list of upcoming meetings
        """
        service = self._get_service()

        now = datetime.utcnow().isoformat() + 'Z'
        end = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'

        events_result = service.events().list(
            calendarId='primary',
            timeMin=now,
            timeMax=end,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Filter only events with attendees (meetings)
        meetings = [e for e in events if e.get('attendees')]

        if not meetings:
            return f"No upcoming meetings in the next {days_ahead} days."

        output = [f"Upcoming meetings (next {days_ahead} days):\n"]
        for meeting in meetings:
            start = meeting['start'].get('dateTime', meeting['start'].get('date'))
            summary = meeting.get('summary', 'No title')
            attendees = meeting.get('attendees', [])
            attendee_emails = [a.get('email', '') for a in attendees if a.get('email')]
            meet_link = meeting.get('hangoutLink', '')

            output.append(f"- {self._format_datetime(start)}: {summary}")
            output.append(f"   Attendees: {', '.join(attendee_emails)}")
            if meet_link:
                output.append(f"   Meet: {meet_link}")
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
        service = self._get_service()

        # Parse date
        if duration_minutes <= 0:
            raise ValueError("Duration must be positive")
        target_date = datetime.strptime(date, '%Y-%m-%d').replace(tzinfo=timezone.utc)
        start_of_day = target_date.replace(hour=9, minute=0, second=0).isoformat()
        end_of_day = target_date.replace(hour=17, minute=0, second=0).isoformat()

        # Get events for the day
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])
        seen = set()
        while events_result.get('nextPageToken'):
            cursor = events_result['nextPageToken']
            if cursor in seen:
                raise ValueError("Calendar returned a repeated page; cannot determine free slots")
            seen.add(cursor)
            events_result = service.events().list(
                calendarId='primary', timeMin=start_of_day, timeMax=end_of_day,
                singleEvents=True, orderBy='startTime', pageToken=cursor,
            ).execute()
            events.extend(events_result.get('items', []))

        # Find gaps
        free_slots = []
        current_time = target_date.replace(hour=9, minute=0)
        end_time = target_date.replace(hour=17, minute=0)

        for event in events:
            if event.get('status') == 'cancelled' or event.get('transparency') == 'transparent':
                continue
            event_start = self._parse_time(event['start'].get('dateTime') or event['start']['date']).replace(tzinfo=timezone.utc)
            event_end = self._parse_time(event['end'].get('dateTime') or event['end']['date']).replace(tzinfo=timezone.utc)
            event_start = min(event_start, end_time)

            # Check if there's a gap before this event
            if (event_start - current_time).total_seconds() >= duration_minutes * 60:
                free_slots.append(f"{current_time.strftime('%I:%M %p')} - {event_start.strftime('%I:%M %p')}")

            current_time = min(end_time, max(current_time, event_end))

        # Check gap at end of day
        if (end_time - current_time).total_seconds() >= duration_minutes * 60:
            free_slots.append(f"{current_time.strftime('%I:%M %p')} - {end_time.strftime('%I:%M %p')}")

        if not free_slots:
            return f"No free slots available on {date} for {duration_minutes} minute meetings."

        return f"Free slots on {date} ({duration_minutes}+ minutes):\n" + "\n".join(f"  - {slot}" for slot in free_slots)

    def _parse_time(self, time_str: str) -> datetime:
        """Parse time string to datetime object.

        Supports formats:
        - ISO: 2024-01-15T14:00:00Z, 2024-01-15T14:00:00
        - Simple: 2024-01-15 14:00

        Args:
            time_str: Time string

        Returns:
            datetime object
        """
        try:
            parsed = datetime.fromisoformat(time_str.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError("Cannot parse time. Use YYYY-MM-DD HH:MM or an ISO timestamp.") from None
        if parsed.tzinfo:
            parsed = parsed.astimezone(timezone.utc).replace(tzinfo=None)
        return parsed
