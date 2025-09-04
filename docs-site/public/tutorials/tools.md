# ConnectOnion Tools

> Built to “show, don’t tell,” with progressive disclosure from simple to advanced.

---

## Quick Start (60 seconds to first tool)

**Three lines to a working tool. Then call it.**

```python
from connectonion import Agent

def search(query: str) -> str:  # your first tool
    return f"Found results for {query}"

agent = Agent(
    "helper", 
    tools=[search],
    max_iterations=5  # Simple search tasks
)
```

**Run it**

```pycon
>>> agent("Find Python tutorials")
'Found results for Python tutorials'
```

That’s it.

---

## Core Concepts (function tools)

What you get:

- Clear interfaces via Python type hints
- Automatic tool schemas for the LLM and UIs
- Docstrings become user-facing descriptions

### Function tools with type hints

Type hints are the interface. Keep signatures explicit.

```python
from connectonion import Agent
from typing import List

def top_k(query: str, k: int = 5) -> List[str]:
    """Return the top-k result titles for a query."""
    # ... your logic ...
    return [f"{i+1}. {query} result" for i in range(k)]

agent = Agent(
    "helper", 
    tools=[top_k],
    max_iterations=8  # May need multiple searches
)
```

**What the agent sees**

```pycon
>>> agent.describe_tools()
[
  {
    "name": "top_k",
    "signature": "top_k(query: str, k: int = 5) -> List[str]",
    "description": "Return the top-k result titles for a query."
  }
]
```
### Return types matter

Use structured returns when the next step needs fields.

```python
from typing import TypedDict, List

class SearchHit(TypedDict):
    title: str
    url: str
    score: float

def search_hits(query: str, k: int = 3) -> List[SearchHit]:
    """Structured results for chaining and UI."""
    return [
        {"title": f"{query} {i}", "url": f"https://example.com/{i}", "score": 0.9 - i*0.1}
        for i in range(k)
    ]
```

**Real output**

```pycon
>>> agent("search_hits('vector db')")
[
  {"title": "vector db 0", "url": "https://example.com/0", "score": 0.9},
  {"title": "vector db 1", "url": "https://example.com/1", "score": 0.8},
  {"title": "vector db 2", "url": "https://example.com/2", "score": 0.7}
]
```

### Docstrings become descriptions

Write the first line as the one‑liner users will read.

```python
def embed(text: str) -> list[float]:
    """Compute a 384-dimensional embedding for text."""
    # ...
```

---

## Stateful Tools (class-based tools)

**✅ RECOMMENDED: Pass the class instance directly to ConnectOnion!**

ConnectOnion automatically discovers all public methods with type hints when you pass a class instance. This is much cleaner than listing methods individually.

Use class instances when tools need shared state, caching, or resources.

### Browser automation with Playwright (navigate, screenshot, tabs)

Requirements:

- Install Playwright and browsers: `pip install playwright` then `playwright install`

```python
from typing import List, Optional
from connectonion import Agent

try:
    from playwright.sync_api import sync_playwright, Page
except ImportError:
    raise SystemExit("Install Playwright: pip install playwright && playwright install")


class Browser:
    """Persistent browser session with navigation, screenshots, and tab control."""

    def __init__(self):
        self._p = None
        self._browser = None
        self._pages: dict[str, Page] = {}
        self._active_tab: Optional[str] = None

    def start(self, headless: bool = True) -> str:
        """Start the browser session and open the first tab named 'main'."""
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch(headless=headless)
        self._pages["main"] = self._browser.new_page()
        self._active_tab = "main"
        return f"Browser started (headless={headless}) with tab 'main'"

    def new_tab(self, name: str) -> str:
        """Open a new tab with a friendly name, e.g., 'docs' or 'shop'."""
        if not self._browser:
            return "Error: Browser not started. Call start() first."
        if name in self._pages:
            return f"Tab '{name}' already exists"
        self._pages[name] = self._browser.new_page()
        self._active_tab = name
        return f"Opened tab '{name}'"

    def list_tabs(self) -> List[str]:
        """List available tab names."""
        return list(self._pages.keys())

    def switch_tab(self, name: str) -> str:
        """Switch the active tab by name."""
        if name not in self._pages:
            return f"Error: No tab named '{name}'"
        self._active_tab = name
        return f"Switched to tab '{name}'"

    def goto(self, url: str, tab: Optional[str] = None) -> str:
        """Navigate the active (or specified) tab to a URL and return the page title."""
        if not self._pages:
            return "Error: Browser not started. Call start() first."
        target = tab or self._active_tab
        page = self._pages[target]
        page.goto(url)
        return page.title()

    def screenshot(self, path: Optional[str] = None, tab: Optional[str] = None) -> str:
        """Save a PNG screenshot of the active (or specified) tab and return the filename."""
        if not self._pages:
            return "Error: Browser not started. Call start() first."
        target = tab or self._active_tab
        page = self._pages[target]
        filename = path or f"{target}_screenshot.png"
        page.screenshot(path=filename)
        return filename

    def close_tab(self, name: str) -> str:
        """Close a tab by name."""
        if name not in self._pages:
            return f"Error: No tab named '{name}'"
        self._pages[name].close()
        del self._pages[name]
        if self._active_tab == name:
            self._active_tab = next(iter(self._pages), None)
        return f"Closed tab '{name}'"

    def close(self) -> None:
        """Close all tabs and stop the browser."""
        for page in list(self._pages.values()):
            page.close()
        self._pages.clear()
        if self._browser:
            self._browser.close()
        if self._p:
            self._p.stop()


browser = Browser()

# ✅ BEST PRACTICE: Pass the class instance directly!
# ConnectOnion automatically extracts all public methods as tools
agent = Agent(
    "helper", 
    tools=[browser],  # Just pass the instance - ConnectOnion does the rest!
    max_iterations=15  # Browser automation often needs more steps
)

# With an LLM, the agent can use natural language prompts to decide which tools to call and in what order.
# For example, you can give the agent a high-level instruction and it will use the available tools to accomplish the task:

response = agent("Open https://example.com, take a screenshot, then open a new tab to https://playwright.dev and screenshot that too. List all open tabs at the end.")
print(response)
    browser.close()
```

### Todo list

```python
class TodoList:
    """Simple todo list with add/list."""
    def __init__(self):
        self._items: list[str] = []

    def add(self, text: str) -> None:
        """Add a new todo item."""
        self._items.append(text)

    def list(self) -> list[str]:
        """Return all todo items."""
        return self._items

todos = TodoList()

# ✅ Two approaches - class instance is cleaner:
# Option 1: Pass individual methods (more verbose)
agent_verbose = Agent("helper", tools=[todos.add, todos.list], max_iterations=10)

# Option 2: Pass class instance (recommended - cleaner!)  
agent = Agent("helper", tools=[todos], max_iterations=10)
```

**Real session**

```pycon
>>> agent("add('buy milk')")
>>> agent("add('book flights')")
>>> agent("list()")
['buy milk', 'book flights']
```

### Resource management

Own the lifecycle. Close things you open. The `Browser` class above
exposes a `close()` method and uses `try/finally` to guarantee cleanup.

---

## Advanced Patterns

### Tool composition

Small tools compose into bigger moves.

```python
def pick_top(hit_list: list[dict]) -> dict:
    """Choose the highest score item."""
    return max(hit_list, key=lambda h: h["score"])

def search_then_pick(query: str) -> dict:
    """Search then pick the best hit."""
    hits = search_hits(query, k=5)
    return pick_top(hits)
```

**Output**

```pycon
>>> agent("search_then_pick('weaviate vs pgvector')")
{'title': 'weaviate vs pgvector 0', 'url': 'https://example.com/0', 'score': 0.9}
```

### Custom tool schemas

Expose structured inputs with clear constraints.

```python
from dataclasses import dataclass
from typing import Annotated, Literal

Priority = Literal["low", "normal", "high"]

@dataclass
class Ticket:
    title: str
    description: str
    priority: Priority
    assignee: Annotated[str, "email"]

def create_ticket(t: Ticket) -> dict:
    """Create a ticket and return its metadata."""
    return {"id": "T-1024", "title": t.title, "priority": t.priority, "assignee": t.assignee}

agent = Agent(
    "helper", 
    tools=[create_ticket],
    max_iterations=5  # Ticket creation is straightforward
)
```

**Schema (example)**

```json
{
  "name": "create_ticket",
  "input": {
    "type": "object",
    "properties": {
      "title": {"type": "string"},
      "description": {"type": "string"},
      "priority": {"enum": ["low", "normal", "high"]},
      "assignee": {"type": "string", "format": "email"}
    },
    "required": ["title", "description", "priority", "assignee"]
  },
  "returns": {"type": "object"}
}
```

---

## Tool Development Guide

### Design rules

* One job per tool. Names are verbs: `search`, `summarize`, `create_ticket`.
* Clean signatures. Prefer primitives and TypedDict/dataclass for structure.
* First docstring line explains the value in plain language.
* Deterministic by default. Document non-determinism.

### Error handling

* Validate inputs. Raise clear exceptions. Return helpful messages.
* Timeouts for IO. Circuit-breakers for flaky deps.
* Log stack traces during development.

### Performance

* Cache pure functions.
* Batch remote calls.
* Stream large outputs when useful.

### Security

* Treat inputs as untrusted.
* Sanitize shell/SQL/HTML.
* Scope credentials. Rotate secrets. Audit access.

### Testing

* Unit-test each tool. Avoid network in tests.
* Golden tests for outputs.
* Fuzz inputs for robustness.

### Versioning and deprecation

* Add `version="1.2.0"` metadata when behavior changes.
* Keep old signatures working until removal.
* Announce removals with dates.

### Authoring checklist

* [ ] Clear name and one-liner
* [ ] Explicit types
* [ ] Real output example
* [ ] Errors handled
* [ ] Tests written

---

## Appendix: Patterns at a glance

* **Function tool** → simplest path to value.
* **Class tool** → shared state, caching, external handles.
* **Composition** → small tools, big outcomes.
* **Custom schemas** → robust interfaces and UIs.

---

## FAQ: How tools are discovered and used

- The agent inspects function signatures and docstrings to build schemas automatically.
- **✅ For class-based tools: Pass the instance directly (not individual methods)!** ConnectOnion automatically extracts all public methods with type hints.
- The first docstring line is used as the one-liner description in UIs.
- Prefer explicit types on parameters and returns so tools are eligible and discoverable.
- You can always call `agent.tool_map["tool_name"](**kwargs)` to run tools without an LLM.

## Class Instance vs Individual Methods

**✅ RECOMMENDED (Clean & Automatic):**
```python
browser = BrowserAutomation()
agent = Agent("browser_agent", tools=[browser])  # Auto-discovers all methods!
```

**❌ VERBOSE (Works but not recommended):**
```python
browser = BrowserAutomation()
agent = Agent("browser_agent", tools=[
    browser.start_browser,
    browser.navigate, 
    browser.take_screenshot,
    browser.scrape_content,
    # ... list every method manually
])
```

ConnectOnion's class instance support makes your code much cleaner and more maintainable!
