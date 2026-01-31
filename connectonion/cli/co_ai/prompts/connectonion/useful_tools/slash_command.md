# SlashCommand

Load and execute custom commands from markdown files.

## Quick Start

```python
from connectonion import SlashCommand

# Load command
cmd = SlashCommand.load("today")

# Get prompt
prompt = cmd.prompt

# List all commands
commands = SlashCommand.list_all()
```

## Command File Format

Create `.co/commands/today.md`:

```markdown
---
name: today
description: Daily email briefing
tools:
  - Gmail.search_emails
  - WebFetch
---
Summarize my important emails from today.
Focus on:
- Urgent requests
- Meeting invites
- Follow-ups needed
```

## YAML Frontmatter

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Command name |
| `description` | Yes | Short description |
| `tools` | No | Allowed tools (all if omitted) |

## Tool Filtering

Limit which tools the command can use:

```yaml
tools:
  - Gmail.search_emails    # Specific method
  - WebFetch               # Whole class
  - my_function            # Standalone function
```

## Locations

Commands are loaded from:
1. `.co/commands/*.md` (user commands - priority)
2. `commands/*.md` (built-in commands)

## API

```python
# Load single command
cmd = SlashCommand.load("today")
cmd.name          # "today"
cmd.description   # "Daily email briefing"
cmd.prompt        # "Summarize my important..."
cmd.tools         # ["Gmail.search_emails", "WebFetch"]

# Filter tools for command
filtered = cmd.filter_tools(all_tools)

# List all available commands
commands = SlashCommand.list_all()
for cmd in commands:
    print(f"/{cmd.name} - {cmd.description}")
```

## Customizing

Need to modify SlashCommand's behavior? Copy the source to your project:

```bash
co copy slash_command
```

Then import from your local copy:

```python
# from connectonion import SlashCommand  # Before
from tools.slash_command import SlashCommand  # After - customize freely!
```
