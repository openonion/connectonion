# ConnectOnion Framework

**Philosophy: "Keep simple things simple, make complicated things possible."**

## Quick Start

```python
from connectonion import Agent

agent = Agent("assistant", tools=[search, read_file, write_file])
result = agent.input("Research microservices and write a summary")
```

## API

```python
agent = Agent(
    name="my_bot",                        # Required: identifier
    tools=[func1, func2],                 # Functions or class instances
    system_prompt="You are helpful",      # String or file path
    model="co/gemini-2.5-pro",            # Default model
    max_iterations=10,                    # Tool call limit per task
    plugins=[plugin1, plugin2],           # Event handlers
)

result = agent.input("task")              # Execute task
```

## CLI Commands

```bash
co create <name>    # Create new agent project
co init             # Initialize in existing directory
co copy <tool>      # Copy built-in tool to customize
co auth             # Authenticate for managed keys
```

## Core Principles

1. **Agent reasons, tools act** - Don't encode logic in tools
2. **Atomic tools** - Small, single-purpose functions
3. **Type hints required** - Agent needs them to understand parameters
4. **Docstrings = descriptions** - First line becomes tool description
5. **Start simple** - Add complexity only when needed

---

## Available Guides

Use `load_guide(path)` to load detailed documentation.

### Core Concepts

| Guide | Description |
|-------|-------------|
| `concepts/agent` | Agent creation, conversations, iterations, lifecycle |
| `concepts/tools` | Function tools, class-based tools, schema generation |
| `concepts/plugins` | Reusable event handlers, custom plugins |
| `concepts/events` | Event system, lifecycle hooks (on_events) |
| `concepts/trust` | Bidirectional trust configuration |
| `concepts/models` | Supported models (OpenAI, Gemini, Claude) |
| `concepts/prompts` | System prompts, file format support |
| `concepts/max_iterations` | Iteration control and limits |
| `concepts/llm_do` | One-shot LLM calls with structured output |
| `concepts/transcribe` | Audio transcription with Gemini |

### Built-in Tools

| Guide | Description |
|-------|-------------|
| `useful_tools/shell` | Shell command execution |
| `useful_tools/diff_writer` | Human-in-the-loop file writing with diffs |
| `useful_tools/todo_list` | Task tracking for multi-step tasks |
| `useful_tools/memory` | Persistent memory using markdown storage |
| `useful_tools/web_fetch` | Web fetching with single-responsibility functions |
| `useful_tools/gmail` | Gmail access for agents |
| `useful_tools/outlook` | Outlook access via Microsoft Graph |
| `useful_tools/google_calendar` | Google Calendar integration |
| `useful_tools/microsoft_calendar` | Microsoft Calendar integration |
| `useful_tools/terminal` | Selection menus, file browser, autocomplete |
| `useful_tools/slash_command` | Custom commands from markdown files |

### Built-in Plugins

| Guide | Description |
|-------|-------------|
| `useful_plugins/re_act` | ReAct pattern - planning and reflection |
| `useful_plugins/eval` | Debug and test prompts during development |
| `useful_plugins/shell_approval` | User approval before shell commands |
| `useful_plugins/image_result_formatter` | Format base64 images for vision models |
| `useful_plugins/gmail_plugin` | Email approval and CRM sync |
| `useful_plugins/calendar_plugin` | Calendar operation approval |

### CLI Reference

| Guide | Description |
|-------|-------------|
| `cli/create` | Create new projects with templates |
| `cli/init` | Initialize in existing directory |
| `cli/copy` | Copy tools and plugins to customize |
| `cli/auth` | Managed models authentication |
| `cli/browser` | Quick browser screenshots |

### Debugging

| Guide | Description |
|-------|-------------|
| `debug/log` | Automatic activity logging |
| `debug/console` | Console output configuration |
| `debug/xray` | See what your agent is thinking |
| `debug/eval` | Run and manage agent evals |
| `debug/auto_debug` | Interactive debugging with breakpoints |
| `debug/exceptions` | AI-powered exception debugging |

### Networking

| Guide | Description |
|-------|-------------|
| `network/host` | Make agent accessible over network |
| `network/connect` | Use remote agents as local |
| `network/deploy` | Deploy agent to production |
| `network/connection` | Client communication from hosted agents |

### TUI Components

| Guide | Description |
|-------|-------------|
| `tui/chat` | Terminal chat interface for agents |
| `tui/input` | Text input with autocomplete |
| `tui/pick` | Single-select menu with keyboard nav |
| `tui/dropdown` | Selection list for autocomplete |
| `tui/status_bar` | Powerline-style status bar |

### Templates

| Guide | Description |
|-------|-------------|
| `templates/minimal` | Simplest starting point |
| `templates/playwright` | Browser automation agent |
| `templates/web-research` | Research and data extraction |
| `templates/meta-agent` | Development assistant |

### Integrations

| Guide | Description |
|-------|-------------|
| `integrations/auth` | Zero-config managed keys |
| `integrations/google` | Gmail and Google Calendar |
| `integrations/microsoft` | Outlook and Microsoft Calendar |

### Reference

| Guide | Description |
|-------|-------------|
| `agent-design` | Agent design best practices |
| `examples` | Copy-paste ready code examples |
| `quickstart` | 60-second quick start |
| `connectonion` | Complete API reference |
| `principles` | Documentation principles |

---

**Load the relevant guide before writing complex ConnectOnion code.**
