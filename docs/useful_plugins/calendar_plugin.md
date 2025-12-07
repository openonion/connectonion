# calendar_plugin

Approval for Google Calendar operations.

## Quick Start

```python
from connectonion import Agent, GoogleCalendar
from connectonion.useful_plugins import calendar_plugin

calendar = GoogleCalendar()
agent = Agent("assistant", tools=[calendar], plugins=[calendar_plugin])

agent.input("Schedule a meeting tomorrow at 2pm")
# ┌─ Create Event ──────────────────┐
# │ Title: Meeting                  │
# │ Start: 2024-01-02 14:00         │
# │ End: 2024-01-02 15:00           │
# │ Attendees: alice@example.com    │
# └─────────────────────────────────┘
# Proceed with create event?
```

## Protected Operations

Requires approval for:
- `create_event` - Create new events
- `create_meet` - Create Google Meet meetings
- `update_event` - Modify existing events
- `delete_event` - Delete events

## Approval Options

- **Yes, {action}** - Proceed once
- **Auto approve all calendar actions** - Auto-approve for session
- **No, tell agent what I want** - Provide feedback

## Events

| Handler | Event | Purpose |
|---------|-------|---------|
| `check_calendar_approval` | `before_each_tool` | Prompt approval before action |

## Session Data

- `agent.current_session['calendar_approve_all']` - Auto-approve flag

## Warnings

The plugin highlights when attendees will be notified:
```
Attendees: alice@example.com (will receive invite!)
```
