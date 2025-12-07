# MicrosoftCalendar

Microsoft Calendar integration via Microsoft Graph API.

## Quick Start

```python
from connectonion import Agent, MicrosoftCalendar

calendar = MicrosoftCalendar()
agent = Agent("assistant", tools=[calendar])

agent.input("What meetings do I have today?")
```

## Setup

Requires Microsoft OAuth authorization:

```bash
co auth microsoft
```

## Methods

### Reading Events

```python
# List upcoming events
calendar.list_events(days_ahead=7, max_results=10)

# Get today's events
calendar.get_today_events()

# Get specific event
calendar.get_event(event_id="abc123")

# Get upcoming meetings
calendar.get_upcoming_meetings(days_ahead=7)

# Find free slots
calendar.find_free_slots(date="2024-01-15", duration_minutes=30)

# Check availability
calendar.check_availability(datetime_str="2024-01-15 14:00")
```

### Creating Events

```python
# Create event
calendar.create_event(
    title="Team Meeting",
    start_time="2024-01-15 14:00",
    end_time="2024-01-15 15:00",
    description="Weekly sync",
    attendees="alice@example.com,bob@example.com",
    location="Conference Room A"
)

# Create Teams meeting
calendar.create_teams_meeting(
    title="Video Call",
    start_time="2024-01-15 14:00",
    end_time="2024-01-15 15:00",
    attendees="alice@example.com",
    description="Quick sync"
)
```

### Managing Events

```python
# Update event
calendar.update_event(
    event_id="abc123",
    title="Updated Title",
    start_time="2024-01-15 15:00"
)

# Delete event
calendar.delete_event(event_id="abc123")
```

## vs GoogleCalendar

| Feature | MicrosoftCalendar | GoogleCalendar |
|---------|------------------|----------------|
| Video calls | Teams | Google Meet |
| Auth | `co auth microsoft` | `co auth google` |
| API | Microsoft Graph | Google Calendar API |
