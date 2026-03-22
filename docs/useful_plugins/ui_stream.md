# ui_stream

Streams agent completion summaries to connected WebSocket UI clients. Used with `host()` for real-time updates in web chat interfaces.

## Usage

```python
from connectonion import Agent, host
from connectonion.useful_plugins import ui_stream

agent = Agent("assistant", plugins=[ui_stream])
host(agent, port=8000)
```

## What it does

When an agent finishes a turn (fires `on_complete`), sends a completion event to the WebSocket client:

```json
{
  "type": "complete",
  "tools_used": ["read_file", "edit", "bash"],
  "llm_calls": 3,
  "iterations": 3
}
```

This lets the frontend show a summary of what the agent did.

## Only active in hosted mode

The plugin checks `if not agent.io: return` — it does nothing when the agent runs locally without a WebSocket connection.

## What other events are streamed

Individual events (thinking, tool results, assistant responses) are emitted directly from the agent and tool executor — `ui_stream` only adds the completion summary.

## When to use

- Building chat UIs with `host()`
- Custom dashboards showing agent activity
- Any web interface that needs real-time completion signals

## Events used

| Event | Handler | Purpose |
|-------|---------|---------|
| `on_complete` | `stream_complete` | Send completion summary to WebSocket |

## Source

```
connectonion/useful_plugins/ui_stream.py
```
