# Watch Events Plugin

`watch_events` inserts claimed events into an Agent that is already running.
It uses `before_iteration` so the next model decision sees the latest event.
If an event arrives during the final model call, `after_iteration` asks the
Agent for one more iteration. The message uses the existing internal
`<system-reminder>` format: it is a model-visible `user` role message, not a
provider `system` role.

```python
from collections import deque

from connectonion import Agent
from connectonion.useful_plugins import watch_events

pending = deque()

def claim_events():
    batch = list(pending)
    pending.clear()
    return batch  # Each item: {"id": "stable-id", "content": "What changed"}

agent = Agent("worker", plugins=[watch_events(claim_events)])
pending.append({"id": "file-42", "content": "notes.md changed"})
agent.input("Check the project")
```

The callback owns its queue and should claim events atomically when multiple
workers may run. The plugin records event IDs in the session trace, marks the
reminder internal for the Host UI, and accepts at most four batches per turn by
default. Use `watch_events(claim_events, max_batches=2)` to change that limit.
The limit resets when the Agent starts another input turn.

An Agent plugin runs only while `Agent.input()` is active. The caller supplies
the event source through `claim_events`. Waking an idle session requires a
running session owner that can start another Agent turn; the plugin does not
start one on its own. `co ai` runs a session-owned watch service for this
purpose. See [co ai watches](../cli/ai.md#watch-work-in-this-session).

To edit the plugin for your own Agent, run `co copy watch_events` and import
`watch_events` from `plugins.watch_events`. The copied file uses absolute
ConnectOnion imports so it works outside the package tree.
