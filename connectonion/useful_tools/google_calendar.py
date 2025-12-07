"""
Purpose: Google Calendar integration tool for managing events and meetings via Google API
LLM-Note:
  Dependencies: imports from [os, datetime, google.oauth2.credentials, googleapiclient.discovery] | imported by [useful_tools/__init__.py] | requires OAuth tokens from 'co auth google' | tested by [tests/unit/test_google_calendar.py]
  Data flow: Agent calls GoogleCalendar methods → _get_credentials() loads tokens from env → builds Calendar API service → API calls to Calendar REST endpoints → returns formatted results (event lists, confirmations, free slots)
  State/Effects: reads GOOGLE_* env vars for OAuth tokens | makes HTTP calls to Google Calendar API | can create/update/delete events | no local file persistence
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
from datetime import datetime, timedelta
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GoogleCalendar:
    """Google Calendar tool for managing events and meetings."""

    def __init__(self):
        """Initialize Google Calendar tool.

        Validates that calendar scope is authorized.
        Raises ValueError if scope is missing.
        """
        scopes = os.getenv("GOOGLE_SCOPES", "")
        if "calendar" not in scopes:
            raise ValueError(
                "Missing 'calendar' scope.\n"
                f"Current scopes: {scopes}\n"
                "Please authorize Google Calendar access:\n"
                "  co auth google"
            )

        self._service = None

    def _get_service(self):
        """Get Google Calendar API service (lazy load with auto-refresh)."""
        access_token = os.getenv("GOOGLE_ACCESS_TOKEN")
        refresh_token = os.getenv("GOOGLE_REFRESH_TOKEN")
        expires_at_str = os.getenv("GOOGLE_TOKEN_EXPIRES_AT")

        if not access_token or not refresh_token:
            raise ValueError(
                "Google OAuth credentials not found.\n"
                "Run: co auth google"
            )

        # Check if token is expired or about to expire (within 5 minutes)
        # Always check before returning cached service
        if expires_at_str:
            from datetime import datetime, timedelta
            expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
            now = datetime.utcnow().replace(tzinfo=expires_at.tzinfo) if expires_at.tzinfo else datetime.utcnow()

            if now >= expires_at - timedelta(minutes=5):
                # Token expired or about to expire, refresh via backend
                access_token = self._refresh_via_backend(refresh_token)
                # Clear cached service to use new token
                self._service = None

        # Return cached service if available
        if self._service:
            return self._service

        # Create credentials
        creds = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=None,
            client_secret=None,
            scopes=["https://www.googleapis.com/auth/calendar"]
        )

        self._service = build('calendar', 'v3', credentials=creds)
        return self._service

    def _refresh_via_backend(self, refresh_token: str) -> str:
        """Refresh access token via backend API.

        Args:
            refresh_token: The refresh token

        Returns:
            New access token
        """
        import httpx

        # Get backend URL and auth
        backend_url = os.getenv("OPENONION_API_URL", "https://oo.openonion.ai")
        api_key = os.getenv("OPENONION_API_KEY")

        if not api_key:
            raise ValueError(
                "OPENONION_API_KEY not found.\n"
                "This is needed to refresh tokens via backend."
            )

        # Call backend refresh endpoint
        response = httpx.post(
            f"{backend_url}/api/v1/oauth/google/refresh",
            headers={"Authorization": f"Bearer {api_key}"},
            json={"refresh_token": refresh_token}
        )

        if response.status_code != 200:
            raise ValueError(
                f"Failed to refresh token via backend: {response.text}"
            )

        data = response.json()
        new_access_token = data["access_token"]
        expires_at = data["expires_at"]

        # Update environment variables for this session
        os.environ["GOOGLE_ACCESS_TOKEN"] = new_access_token
        os.environ["GOOGLE_TOKEN_EXPIRES_AT"] = expires_at

        # Update .env file if it exists
        env_file = os.path.join(os.getenv("AGENT_CONFIG_PATH", os.path.expanduser("~/.co")), "keys.env")
        if os.path.exists(env_file):
            with open(env_file, 'r') as f:
                lines = f.readlines()

            with open(env_file, 'w') as f:
                for line in lines:
                    if line.startswith("GOOGLE_ACCESS_TOKEN="):
                        f.write(f"GOOGLE_ACCESS_TOKEN={new_access_token}\n")
                    elif line.startswith("GOOGLE_TOKEN_EXPIRES_AT="):
                        f.write(f"GOOGLE_TOKEN_EXPIRES_AT={expires_at}\n")
                    else:
                        f.write(line)

        return new_access_token

    def _format_datetime(self, dt_str: str) -> str:
        """Format datetime string to readable format."""
        dt = datetime.fromisoformat(dt_str.replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %I:%M %p')

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
            output.append(f"Attendees:\n  " + "\n  ".join(attendee_list))

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

        if attendees:
            attendee_list = [{'email': email.strip()} for email in attendees.split(',')]
            event['attendees'] = attendee_list

        created_event = service.events().insert(
            calendarId='primary',
            body=event
        ).execute()

        return f"Event created: {title}\nStart: {self._format_datetime(start_dt.isoformat())}\nEvent ID: {created_event['id']}\nLink: {created_event.get('htmlLink', '')}"

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

        attendee_list = [{'email': email.strip()} for email in attendees.split(',')]

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
            conferenceDataVersion=1
        ).execute()

        meet_link = created_event.get('hangoutLink', 'No Meet link generated')

        return f"Meeting created: {title}\nStart: {self._format_datetime(start_dt.isoformat())}\nMeet link: {meet_link}\nEvent ID: {created_event['id']}"

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
            attendee_list = [{'email': email.strip()} for email in attendees.split(',')]
            event['attendees'] = attendee_list

        updated_event = service.events().update(
            calendarId='primary',
            eventId=event_id,
            body=event
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
            eventId=event_id
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
        target_date = datetime.strptime(date, '%Y-%m-%d')
        start_of_day = target_date.replace(hour=9, minute=0, second=0).isoformat() + 'Z'
        end_of_day = target_date.replace(hour=17, minute=0, second=0).isoformat() + 'Z'

        # Get events for the day
        events_result = service.events().list(
            calendarId='primary',
            timeMin=start_of_day,
            timeMax=end_of_day,
            singleEvents=True,
            orderBy='startTime'
        ).execute()

        events = events_result.get('items', [])

        # Find gaps
        free_slots = []
        current_time = target_date.replace(hour=9, minute=0)
        end_time = target_date.replace(hour=17, minute=0)

        for event in events:
            event_start = datetime.fromisoformat(event['start'].get('dateTime', '').replace('Z', '+00:00'))
            event_end = datetime.fromisoformat(event['end'].get('dateTime', '').replace('Z', '+00:00'))

            # Check if there's a gap before this event
            if (event_start - current_time).total_seconds() >= duration_minutes * 60:
                free_slots.append(f"{current_time.strftime('%I:%M %p')} - {event_start.strftime('%I:%M %p')}")

            current_time = max(current_time, event_end)

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
        for fmt in ['%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M']:
            try:
                return datetime.strptime(time_str, fmt)
            except ValueError:
                continue

        raise ValueError(f"Cannot parse time: {time_str}. Use format: YYYY-MM-DD HH:MM or ISO format")
