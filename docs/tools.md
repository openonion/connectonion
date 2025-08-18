# ConnectOnion Tools

> Built to “show, don’t tell,” with progressive disclosure from simple to advanced.

---

## Quick Start (60 seconds to first tool)

**Three lines to a working tool. Then call it.**

```python
def search(query: str) -> str:  # your first tool
    return f"Found results for {query}"

agent = Agent("helper", tools=[search])
```

**Run it**

```pycon
>>> agent("Find Python tutorials")
'Found results for Python tutorials'
```

That’s it.

---

## Core Concepts (function tools)

### Function tools with type hints

Type hints are the interface. Keep signatures explicit.

```python
from typing import List

def top_k(query: str, k: int = 5) -> List[str]:
    """Return the top-k result titles for a query."""
    # ... your logic ...
    return [f"{i+1}. {query} result" for i in range(k)]

agent = Agent("helper", tools=[top_k])
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

Use class instances when tools need shared state, caching, or resources.

### Browser automation with Playwright

```python
from playwright.sync_api import sync_playwright

class Browser:
    """Persistent browser session with goto()."""
    def __init__(self):
        self._p = sync_playwright().start()
        self._browser = self._p.chromium.launch()
        self._page = self._browser.new_page()

    def goto(self, url: str) -> str:
        """Navigate to a URL and return the page title."""
        self._page.goto(url)
        return self._page.title()

    def close(self) -> None:
        self._browser.close()
        self._p.stop()

browser = Browser()
agent = Agent("helper", tools=[browser.goto])
try:
    agent("goto('https://example.com')")
finally:
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
agent = Agent("helper", tools=[todos.add, todos.list])
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

agent = Agent("helper", tools=[create_ticket])
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
