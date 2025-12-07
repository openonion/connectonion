# Built-in Tools

Pre-built tools for common agent tasks.

## Quick Reference

| Tool | Purpose | Import |
|------|---------|--------|
| [Shell](shell.md) | Execute shell commands | `from connectonion import Shell` |
| [DiffWriter](diff_writer.md) | Edit files with diffs | `from connectonion import DiffWriter` |
| [TodoList](todo_list.md) | Track task progress | `from connectonion import TodoList` |
| [WebFetch](web_fetch.md) | Fetch web content | `from connectonion import WebFetch` |
| [Gmail](gmail.md) | Gmail integration | `from connectonion import Gmail` |
| [get_emails](get_emails.md) | Email parsing utilities | `from connectonion import get_emails` |
| [send_email](send_email.md) | Send emails via API | `from connectonion import send_email` |
| [Outlook](outlook.md) | Outlook integration | `from connectonion import Outlook` |
| [GoogleCalendar](google_calendar.md) | Google Calendar | `from connectonion import GoogleCalendar` |
| [MicrosoftCalendar](microsoft_calendar.md) | Microsoft Calendar | `from connectonion import MicrosoftCalendar` |
| [Memory](memory.md) | Persistent memory | `from connectonion import Memory` |
| [Terminal](terminal.md) | Interactive terminal | `from connectonion import Terminal` |
| [SlashCommand](slash_command.md) | Custom commands | `from connectonion import SlashCommand` |

## Usage Pattern

```python
from connectonion import Agent, Shell, DiffWriter

# Create tool instances
shell = Shell()
writer = DiffWriter()

# Pass to agent
agent = Agent("coder", tools=[shell, writer])

agent.input("Create a hello.py file that prints 'Hello World'")
```

## Categories

### File Operations
- **Shell** - Run commands, scripts, git
- **DiffWriter** - Edit files with visual diffs

### Communication
- **Gmail** - Send/read Gmail
- **Outlook** - Send/read Outlook

### Calendar
- **GoogleCalendar** - Google Calendar events
- **MicrosoftCalendar** - Microsoft Calendar events

### Utilities
- **WebFetch** - Fetch and parse web pages
- **Memory** - Store/retrieve persistent data
- **TodoList** - Track tasks and progress
- **Terminal** - Interactive terminal UI
- **SlashCommand** - Define custom commands
