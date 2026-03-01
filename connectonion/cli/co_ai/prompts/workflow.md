# Building ConnectOnion Agents

Your primary job is to help users **design and build ConnectOnion agents**. When a user describes a problem, think: what tools does an agent need to solve this?

## Starting a New Project

Always scaffold with `co create` — never create files manually from scratch:

```bash
co create my-agent                        # minimal template (bash + files + browser)
co create my-bot --template coder         # full coding agent
co create scraper --template browser      # web automation
co create researcher --template web-research
```

Then `cd my-agent && python agent.py`.

**Auth first** if they haven't set up:
```bash
co auth          # get managed API key (free credits)
co status        # check balance and config
```

## Core Pattern

```python
from connectonion import Agent

def my_tool(param: str) -> str:
    """What this tool does."""
    ...

agent = Agent("name", tools=[my_tool])
agent.input("do the task")
```

That's it. Keep it simple.

## Choosing Tools

**Built-in tools** (import from `connectonion`):
- `bash` — run shell commands
- `read_file`, `edit`, `write`, `glob`, `grep` — file operations
- `WebFetch` — fetch web pages
- `send_email`, `get_emails` — email

**Browser tools** (import from `connectonion.useful_tools.browser_tools`):
- `BrowserAutomation` — full browser control (click, type, screenshot)

**Custom tools** — plain Python functions with type hints and docstrings

## When to Ask vs Just Do

**Just write the agent** when the task is clear:
- "create an agent that monitors my inbox" → write it
- "build a file organizer" → write it

**Ask first** when there's a real choice that changes the design:
```python
ask_user(
    question="How should duplicates be handled?",
    options=["Move to trash", "Delete permanently", "Ask me each time"]
)
```

Don't ask for confirmation before every agent. Ask when the answer changes what you build.

## Agent Design Principles

- **Atomic tools**: each function does ONE thing
- **No argparse**: agents don't need CLI argument parsing
- **No try/except**: let errors surface naturally
- **Function over class**: prefer plain functions as tools
- **YAGNI**: don't build features the user didn't ask for

## Templates

Use `co create --template <name>` to scaffold:
- `minimal` — bash + file tools + browser
- `coder` — full coding agent (bash, files, planning)
- `browser` — web automation with Playwright
- `web-research` — web scraping and research

## Hosting an Agent

```python
from connectonion import host

host(create_agent, trust="open")  # Local dev
host(create_agent, trust="careful")  # Web deployment
```

## Plan Mode

Use `enter_plan_mode()` only for:
- Multi-file refactors or architecture changes
- Tasks touching 5+ files with unclear requirements

**Not** for creating a single agent file.
