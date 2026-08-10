---
name: build
intent: build
---

<system-reminder>
Agent creation detected. Use the workflow: clarify real design choices → use todos for complex work → `co create` → edit agent.py → verify it

ConnectOnion agents are Python files that give tools to the AI rather than hardcoded logic. The agent decides its own strategy. After scaffolding with `co create`, the structure looks like:

```python
from connectonion import Agent

def list_files(dir: str) -> list[str]: ...
def get_hash(path: str) -> str: ...
def delete(path: str) -> str: ...

agent = Agent("cleaner", tools=[list_files, get_hash, delete])
agent.input("Remove duplicate files")
```

For a simple agent, scaffold and edit directly. For work with three or more meaningful steps, create a todo list first and keep it current. Always scaffold with `co create`; do not create the project structure manually.
</system-reminder>
