---
name: build
intent: build
---

<system-reminder>
Agent creation detected. Use ConnectOnion framework:

**ConnectOnion agents are Python files (.py), NOT markdown files.**

```python
from connectonion import Agent

def list_files(dir: str) -> list[str]: ...
def get_hash(path: str) -> str: ...
def delete(path: str) -> str: ...

agent = Agent("cleaner", tools=[list_files, get_hash, delete])
agent.input("Remove duplicate files")
```

**Give tools, not logic. Let the agent decide strategy. NEVER create standalone scripts with hardcoded logic.**
</system-reminder>
