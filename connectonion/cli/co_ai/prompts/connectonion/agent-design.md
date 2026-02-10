# Agent Design Guide

How to design robust ConnectOnion agents.

## Decision Tree: How to Create an Agent

```
User wants an agent
        │
        ▼
┌─────────────────────────────────┐
│ Does a template exist?          │
│ (playwright, email-agent,       │
│  web-research, meta-agent)      │
└───────────┬─────────────────────┘
            │
    ┌───────┴───────┐
    │Yes            │No
    ▼               ▼
┌─────────┐   ┌─────────────────────────┐
│ co create│   │ Is it simple (2-4 tools)?│
│ --template│   └───────────┬─────────────┘
└─────────┘             │
                ┌───────┴───────┐
                │Yes            │No
                ▼               ▼
        ┌─────────────┐   ┌─────────────────┐
        │Write directly│   │Load guide,      │
        │(one file)   │   │write with class │
        └─────────────┘   └─────────────────┘
```

## One-Shot Agent Creation

**Simple agents (2-4 tools) → Write directly:**
```python
# /tmp/calc/agent.py - complete file
from connectonion import Agent

def add(a: float, b: float) -> float:
    """Add two numbers."""
    return a + b

def multiply(a: float, b: float) -> float:
    """Multiply two numbers."""
    return a * b

agent = Agent("calculator", tools=[add, multiply])

if __name__ == "__main__":
    agent.input("What is 5 + 3?")
```

**Complex agents (5+ tools, shared state) → Use class:**
```python
# /tmp/browser/agent.py - with class for stateful tools
from connectonion import Agent

class Browser:
    def __init__(self):
        self.page = None

    def navigate(self, url: str) -> str:
        """Go to URL."""
        # ... implementation

    def screenshot(self) -> str:
        """Take screenshot."""
        # ... implementation

    def click(self, selector: str) -> str:
        """Click element."""
        # ... implementation

browser = Browser()
agent = Agent("browser", tools=[browser], system_prompt="prompt.md")
```

**With built-in tools → Import and use:**
```python
from connectonion import Agent, Gmail, WebFetch

gmail = Gmail()
web = WebFetch()

agent = Agent("assistant", tools=[gmail, web])
```

## File Structure by Complexity

**Simple (2-4 tools) → Single file:**
```
my-agent/
└── agent.py          # Everything in one file
```

**Medium (5-8 tools) → Split tool class:**
```
my-agent/
├── agent.py          # Main entry, Agent setup
├── tools.py          # Tool class with methods
└── prompt.md         # System prompt
```

**Complex (8+ tools, production) → Full structure:**
```
my-agent/
├── agent.py          # Main entry with interactive loop
├── tools/
│   ├── __init__.py
│   └── browser.py    # Tool class
├── prompts/
│   └── agent.md      # System prompt
├── CLAUDE.md         # AI guidance for maintaining this project
├── pyproject.toml    # Dependencies
├── tests/            # Test suite
└── README.md         # Usage docs
```

**CLAUDE.md for Production:**
Add this file so AI assistants understand the project:
```markdown
# CLAUDE.md
## Project Overview
What this agent does and its core philosophy.

## Architecture
- Tool layer: tools/*.py
- Agent layer: agent.py
- Prompts: prompts/*.md

## Development Commands
- How to run, test, deploy

## Key Patterns
- How to add new tools
- Error handling approach
```

## 1. Start with CLI

**Check available commands:**

```bash
co --help
```

**Create new projects (use when template matches):**

```bash
co create my-agent
cd my-agent

# With template
co create my-browser --template playwright
co create my-emailer --template email-agent
co create my-researcher --template web-research
```

**Project structure:**

```
my-agent/
├── agent.py          # Your agent code
├── prompts/
│   └── agent.md      # System prompt (for complex agents)
├── .env              # API keys (auto-copied from ~/.co/)
└── .co/              # Metadata
```

## 2. System Prompt: Markdown Files

**Always use separate markdown files:**

```python
agent = Agent("assistant", system_prompt="prompts/agent.md", tools=[...])
```

## 3. Built-in Tools First

**Check built-in tools before writing custom:**

```bash
# See available tools
co copy --list
```

```python
from connectonion import Agent, Shell, Gmail, Memory, WebFetch, DiffWriter, TodoList

agent = Agent("assistant", tools=[Shell(), Gmail(), Memory()])
```

**Need to customize? Copy and modify:**

```bash
co copy Gmail        # Creates ./tools/gmail.py
co copy Shell        # Creates ./tools/shell.py
```

```python
from tools.gmail import Gmail  # Use your customized version
```

## 4. Plugins for Behavior

**Use built-in plugins:**

```bash
co copy --list  # See available plugins
```

```python
from connectonion.useful_plugins import re_act, shell_approval

agent = Agent("researcher", tools=[search], plugins=[re_act])
```

**Copy and customize:**

```bash
co copy re_act       # Creates ./plugins/re_act.py
```

## 5. Tools: Function vs Class

**Functions for stateless:**

```python
def search(query: str) -> str:
    """Search the web."""
    return do_search(query)
```

**Classes for shared state:**

```python
class Browser:
    def __init__(self):
        self._page = None

    def navigate(self, url: str) -> str:
        """Go to URL."""
        self._page = open_page(url)
        return self._page.title

    def screenshot(self) -> str:
        """Screenshot current page."""
        return self._page.screenshot()

browser = Browser()
agent = Agent("browser", tools=[browser])  # Pass instance
```

## 6. Events for Custom Logic

```python
from connectonion import Agent, after_llm, after_tools

def log_timing(agent):
    trace = agent.current_session['trace'][-1]
    print(f"LLM: {trace['duration_ms']}ms")

agent = Agent("assistant", on_events=[after_llm(log_timing)])
```

## 7. Tool Design Rules

**One tool = one action:**

```python
# GOOD
def list_files(dir: str) -> str: ...
def read_file(path: str) -> str: ...
def delete_file(path: str) -> str: ...

# BAD
def file_manager(action: str, path: str) -> str: ...
```

**Verb_noun names:**

```python
def send_email(...): ...
def search_web(...): ...
def create_ticket(...): ...
```

**Informative returns:**

```python
def delete_file(path: str) -> str:
    os.remove(path)
    return f"Deleted {path}"  # Not just "Done"
```

**Errors as messages:**

```python
def read_file(path: str) -> str:
    if not os.path.exists(path):
        return f"File not found: {path}"
    return Path(path).read_text()
```

## 8. Tool Count

| Complexity | Tools | Example |
|------------|-------|---------|
| Simple | 2-4 | Calculator |
| Medium | 4-8 | File manager |
| Complex | Sub-agents | Research + Writing |

## Quick Checklist

- [ ] `co create my-agent` to start
- [ ] System prompt in `prompts/agent.md`
- [ ] `co copy --list` to check built-in tools
- [ ] `co copy ToolName` to customize
- [ ] One action per tool
- [ ] 2-8 tools per agent
