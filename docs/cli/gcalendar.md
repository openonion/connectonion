# co gcalendar

Run `co auth google`, then `co gcalendar list`. Event IDs are stable IDs, not row numbers.

| Command | Python method on GoogleCalendar |
|---|---|
| `list --days 7 --last 20` | `list_events` |
| `today` | `get_today_events` |
| `read EVENT_ID` | `get_event` |
| `meetings --days 7` | `get_upcoming_meetings` |
| `free 2026-09-07 --minutes 30` | `find_free_slots` |
| `create TITLE START END` | `create_event` |
| `meet TITLE START END --attendees EMAILS` | `create_meet` |
| `update EVENT_ID --title TITLE` | `update_event` |
| `delete EVENT_ID` | `delete_event` |

Bare `co gcalendar` lists upcoming events. Each command's `--help` lists options.
Create, Meet, update and delete preview by default; `--yes` performs the write.
A preview shows arguments, not proof of account access. Inspect account state
after an uncertain write before retrying.

ISO offsets normalize to UTC; naive times mean UTC. Primary calendar only.
Free slots cover 09:00–17:00 UTC, all result pages and all-day busy events, not
other attendees' calendars. Updates preserve omitted fields; empty strings do
not clear fields.

Exit 0 is a read, preview or successful write response; 1 is an operational
failure with recovery guidance; 2 is invalid arguments. Output ends in one next
command, including when piped. See [Google auth](../integrations/google.md).
