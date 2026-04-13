# co copy - Copy Tools, Plugins, Skills & Prompts

Copy built-in tools, plugins, skills, and prompt templates to your project for customization.

## Quick Start

```bash
# See what's available
co copy --list

# Copy a tool
co copy Gmail

# Copy a plugin
co copy re_act

# Copy a skill (installs to .co/skills/, usable as /ship-feature)
co copy ship-feature

# Copy a prompt template
co copy coding_agent
```

## Why Copy?

Built-in tools work great out of the box. But sometimes you need to:

- **Add features** - Extend functionality for your use case
- **Modify behavior** - Change how a tool works
- **Learn** - Study implementation patterns
- **Debug** - Trace issues in tool code

Copying gives you full control over the source code.

## Usage

### List Available Items

```bash
co copy --list
```

Output:
```
                    Available Items to Copy
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃ Name                   ┃ Type   ┃ Path                      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ gmail                  │ tool   │ gmail.py                  │
│ memory                 │ tool   │ memory.py                 │
│ shell                  │ tool   │ shell.py                  │
│ ...                    │        │                           │
│ re_act                 │ plugin │ re_act.py                 │
│ shell_approval         │ plugin │ shell_approval.py         │
│ coding_agent           │ prompt │ coding_agent/             │
└────────────────────────┴────────┴───────────────────────────┘
```

### Copy a Tool

```bash
co copy Gmail
```

Creates `./tools/gmail.py` in your project.

### Copy a Plugin

```bash
co copy re_act
```

Creates `./plugins/re_act.py` in your project.

### Copy a Prompt Template

```bash
co copy coding_agent
```

Creates `./prompts/coding_agent/` directory with:
```
prompts/coding_agent/
├── prompts/
│   ├── main.md           # Core agent behavior
│   └── tools/            # Per-tool guidance
│       ├── shell.md
│       ├── read.md
│       ├── write.md
│       └── todo.md
├── assembler.py          # Prompt assembly utility
└── README.md
```

### Copy Multiple Items

```bash
co copy Gmail Shell memory re_act
```

### Custom Destination

```bash
co copy Gmail --path ./my_tools/
```

### Force Overwrite

```bash
co copy Gmail --force
```

## Available Tools

| Name | File | Description |
|------|------|-------------|
| ask_user | ask_user.py | Ask user for input during agent execution |
| bash | bash.py | Bash command execution (Unix/Mac) |
| diff_writer | diff_writer.py | File editing with diffs |
| get_emails | get_emails.py | Fetch emails from inbox |
| gmail | gmail.py | Gmail integration (OAuth, send/receive) |
| google_calendar | google_calendar.py | Google Calendar events |
| memory | memory.py | Persistent agent memory |
| microsoft_calendar | microsoft_calendar.py | Microsoft Calendar |
| outlook | outlook.py | Outlook/Microsoft email |
| send_email | send_email.py | Send emails |
| shell | shell.py | Shell command execution (cross-platform) |
| slash_command | slash_command.py | Custom command extension |
| terminal | terminal.py | Interactive terminal sessions |
| todo_list | todo_list.py | Task list management |
| web_fetch | web_fetch.py | Web scraping tool |

## Available Plugins

| Name | File | Description |
|------|------|-------------|
| auto_compact | auto_compact.py | Auto-compress context when nearing limit |
| calendar_plugin | calendar_plugin.py | Google Calendar integration |
| eval | eval.py | Task completion evaluation |
| gmail_plugin | gmail_plugin.py | Gmail OAuth flow |
| image_result_formatter | image_result_formatter.py | Base64 image handling |
| prefer_write_tool | prefer_write_tool.py | Guide agent to prefer write tool over shell |
| re_act | re_act.py | ReAct prompting pattern |
| shell_approval | shell_approval.py | User confirmation for shell commands |
| skills | skills.py | Auto-discover and load skills (.co/skills/, .claude/skills/) |
| subagents | subagents.py | Sub-agent task delegation |
| system_reminder | system_reminder.py | Inject contextual reminders into tool results |
| ui_stream | ui_stream.py | Stream agent output to UI |
| ulw | ulw.py | Ultra Light Work - autonomous continuous execution |

### Plugins with Prompts

Some plugins include prompt files. These are automatically copied together:

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

## After Copying

### Update Your Imports

```python
# Before (from package)
from connectonion import Gmail

# After (from your copy)
from tools.gmail import Gmail
```

### Customize the Code

Now you have full control:

```python
# tools/gmail.py - Your copy, modify freely!

class Gmail:
    def send(self, to, subject, body):
        # Add your custom logic here
        self.log_to_my_system(to, subject)  # Your addition
        # ... rest of original code
```

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--list` | `-l` | List available tools and plugins |
| `--path` | `-p` | Custom destination path |
| `--force` | `-f` | Overwrite existing files |

## Examples

### Customize Gmail Tool

```bash
# Copy Gmail tool
co copy gmail

# Edit your copy
# tools/gmail.py
```

```python
# agent.py
from tools.gmail import Gmail  # Use your customized version

agent = Agent("emailer", tools=[Gmail()])
```

### Create Custom Plugin

```bash
# Copy re_act as starting point
co copy re_act

# Modify plugins/re_act.py for your needs
```

### Copy All Email Tools

```bash
co copy gmail outlook
```

## Available TUI Components

| Name | File | Description |
|------|------|-------------|
| chat | chat.py | Chat interface component |
| divider | divider.py | Visual divider component |
| dropdown | dropdown.py | Dropdown selector |
| footer | footer.py | Footer bar component |
| fuzzy | fuzzy.py | Fuzzy search component |
| input | input.py | Text input component |
| keys | keys.py | Key binding handler |
| pick | pick.py | Item picker component |
| providers | providers.py | Model provider selector |
| status_bar | status_bar.py | Status bar component |

## Available Prompts

| Name | Directory | Description |
|------|-----------|-------------|
| coding_agent | coding_agent/ | Coding Agent Prompt - modular prompt template for coding assistants |
| cc_prompt | cc_prompt/ | Claude Code System Prompt - 250 prompt pieces organized by category |

## Available Skills

Skills are copied to `.co/skills/<name>/` and auto-discovered by the skills plugin as `/skill-name`.

| Name | Description |
|------|-------------|
| ship-feature | Ship a feature end-to-end — update tests, docs, docs-site, then release to PyPI |

```bash
co copy ship-feature
# → .co/skills/ship-feature/SKILL.md
# → invoke with /ship-feature
```

## Available Trust Policies

| Name | File | Description |
|------|------|-------------|
| trust/open | open.md | Development - allow all requests |
| trust/careful | careful.md | Testing - whitelist + LLM for unknowns |
| trust/strict | strict.md | Production - whitelist only |

## See Also

- [Built-in Tools](../useful_tools/) - Tool documentation
- [Built-in Plugins](../useful_plugins/) - Plugin documentation
- [Prompt Templates](../useful_prompts/) - Prompt documentation
- [Creating Tools](../concepts/tools.md) - Writing custom tools
