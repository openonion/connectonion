---
name: build
intent: build
---

<system-reminder>
Agent creation detected. Use the workflow: enter plan mode → design spec → get approval → `co create` → edit agent.py

ConnectOnion agents are Python files that give tools to the AI rather than hardcoded logic. The agent decides its own strategy. After scaffolding with `co create`, the structure looks like:

```python
from connectonion import Agent

def list_files(dir: str) -> list[str]: ...
def get_hash(path: str) -> str: ...
def delete(path: str) -> str: ...

agent = Agent("cleaner", tools=[list_files, get_hash, delete])
agent.input("Remove duplicate files")
```

Start with `enter_plan_mode()` to design the spec before creating files.
</system-reminder>
