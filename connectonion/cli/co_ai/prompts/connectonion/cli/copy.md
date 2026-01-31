# co copy - Copy Tools & Plugins

Copy built-in tools and plugins to your project for customization.

## Quick Start

```bash
# See what's available
co copy --list

# Copy a tool
co copy Gmail

# Copy a plugin
co copy re_act
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
┃ Name                   ┃ Type   ┃ File                      ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇━━━━━━━━━━━━━━━━━━━━━━━━━━━┩
│ gmail                  │ tool   │ gmail.py                  │
│ memory                 │ tool   │ memory.py                 │
│ shell                  │ tool   │ shell.py                  │
│ ...                    │        │                           │
│ re_act                 │ plugin │ re_act.py                 │
│ shell_approval         │ plugin │ shell_approval.py         │
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
| gmail | gmail.py | Gmail integration (OAuth, send/receive) |
| outlook | outlook.py | Outlook/Microsoft email |
| google_calendar | google_calendar.py | Google Calendar events |
| microsoft_calendar | microsoft_calendar.py | Microsoft Calendar |
| memory | memory.py | Persistent agent memory |
| web_fetch | web_fetch.py | Web scraping tool |
| shell | shell.py | Shell command execution |
| diff_writer | diff_writer.py | File editing with diffs |
| todo_list | todo_list.py | Task list management |
| slash_command | slash_command.py | Custom command extension |

## Available Plugins

| Name | File | Description |
|------|------|-------------|
| re_act | re_act.py | ReAct prompting pattern |
| eval | eval.py | Evaluation plugin |
| image_result_formatter | image_result_formatter.py | Base64 image handling |
| shell_approval | shell_approval.py | User confirmation for shell |
| gmail_plugin | gmail_plugin.py | Gmail OAuth flow |
| calendar_plugin | calendar_plugin.py | Google Calendar integration |

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

## See Also

- [Built-in Tools](../useful_tools/) - Tool documentation
- [Built-in Plugins](../useful_plugins/) - Plugin documentation
- [Creating Tools](../concepts/tools.md) - Writing custom tools
