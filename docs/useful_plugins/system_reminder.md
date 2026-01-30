# System Reminder Plugin

Inject contextual guidance into tool results to nudge agent behavior.

## Quick Start

```python
from connectonion import Agent
from connectonion.useful_plugins import system_reminder

agent = Agent("assistant", tools=[...], plugins=[system_reminder])
```

## Concept

System reminders are short messages appended to tool results that guide the agent's next action—without extra API calls or separate messages.

**Example**: After writing a Python file, remind the agent to consider testing.

```
write_file("app.py", code)
    ↓
Result: "File written successfully"
    ↓
With system reminder: "File written successfully

    <system-reminder>
    Consider running tests to verify your changes work correctly.
    This is a gentle reminder - ignore if not applicable.
    </system-reminder>"
```

The LLM sees the system reminder as part of the tool output and naturally considers it.

## How It Works

```
┌─────────────────────────────────────────────┐
│          SYSTEM REMINDER FLOW                │
├─────────────────────────────────────────────┤
│                                             │
│  1. Tool executes (e.g., write_file)        │
│                 ↓                           │
│  2. after_each_tool event fires             │
│                 ↓                           │
│  3. Plugin checks triggers:                 │
│     - tool name matches?                    │
│     - path pattern matches?                 │
│                 ↓                           │
│  4. If match: append system reminder        │
│                 ↓                           │
│  5. LLM sees result + system reminder       │
│                                             │
└─────────────────────────────────────────────┘
```

## Categories

Based on Claude Code patterns, system reminders fall into five categories:

| Category | Purpose | Example |
|----------|---------|---------|
| **Workflow Nudges** | Gentle best practice suggestions | "Consider running tests" |
| **State Notifications** | Inform about state changes | "You exited plan mode" |
| **External Events** | React to external changes | "File was modified by linter" |
| **Next Steps** | Guide what to do next | "Verify your implementation" |
| **Context Injection** | Provide relevant info | "This file contains secrets" |

## File Format

Each system reminder is a markdown file with YAML frontmatter:

```markdown
---
name: test-reminder
triggers:
  - tool: write_file
    path_pattern: "*.py"
---

<system-reminder>
Consider running tests to verify your changes.
This is a gentle reminder - ignore if not applicable.
</system-reminder>
```

### Frontmatter Fields

| Field | Required | Description |
|-------|----------|-------------|
| `name` | Yes | Unique identifier |
| `triggers` | Yes | List of trigger conditions |
| `triggers[].tool` | No | Tool name to match |
| `triggers[].path_pattern` | No | Glob pattern(s) for file path arguments |
| `triggers[].command_pattern` | No | Glob pattern(s) for command arguments |

### Variables

Use `${variable}` for dynamic content:

| Variable | Description |
|----------|-------------|
| `${file_path}` | File path from tool arguments |
| `${tool_name}` | Name of the tool that fired |

## Design Principles

**Gentle, Not Forceful**
- ✓ "Consider running tests"
- ✗ "You MUST run tests now"

**Contextual, Not Spammy**
- Fire only when relevant, not after every tool call

**Simple Patterns**
- Use glob: `*.py`, `["*.env", "*secret*"]`
- Not regex: `.*\.py$`

## Customizing

Copy the plugin and built-in reminders to your project:

```bash
co copy system_reminder
```

Creates:
```
./plugins/system_reminder.py
./prompts/system-reminders/
├── test-reminder.md
└── security-warning.md
```

Then import from your local copy:

```python
from plugins.system_reminder import system_reminder
agent = Agent("assistant", plugins=[system_reminder])
```

Modify the reminder files in `./prompts/system-reminders/` to customize.

---

## Examples

### Workflow Nudge: Test After Code Change

```markdown
---
name: test-reminder
triggers:
  - tool: write_file
    path_pattern: ["*.py", "*.js", "*.ts"]
---

<system-reminder>
Code was modified. Consider:
- Running relevant tests
- Checking for linter errors
This is a gentle reminder - ignore if not applicable.
</system-reminder>
```

### State Notification: Plan Mode Exited

```markdown
---
name: plan-mode-exited
triggers:
  - tool: exit_plan_mode
---

<system-reminder>
You have exited plan mode. You can now make edits and run tools.
</system-reminder>
```

### External Event: File Modified Externally

```markdown
---
name: file-modified-externally
triggers:
  - tool: file_watcher
---

<system-reminder>
${file_path} was modified externally (by user or linter).
Don't revert these changes unless asked.
</system-reminder>
```

### Context Injection: Security Warning

```markdown
---
name: security-warning
triggers:
  - tool: read_file
    path_pattern: ["*.env", "*secret*", "*.pem"]
---

<system-reminder>
This file may contain sensitive information.
- Never expose secrets in output
- Never commit real credentials
</system-reminder>
```
