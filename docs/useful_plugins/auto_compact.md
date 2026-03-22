# auto_compact

Automatically compresses the agent's context window when it reaches 90% capacity, preventing token overflow and keeping long sessions alive.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import auto_compact

agent = Agent("assistant", plugins=[auto_compact])
```

## What it does

When the context window hits 90% full:
1. Summarizes old messages into a single compact message using `co/gemini-2.5-flash`
2. Replaces old messages with the summary (keeps system prompt + summary + last 5 messages)
3. Continues the session without interruption

## How it triggers

Fires on the `after_llm` event after every LLM response. Only activates when:
- Context usage >= 90%
- At least 8 messages in the session

## Example

A long research session that would normally hit token limits:

```python
from connectonion import Agent
from connectonion.useful_plugins import auto_compact

agent = Agent("researcher", plugins=[auto_compact], model="co/gemini-2.5-pro")

# Works even on very long sessions
for topic in topics:
    agent.input(f"Research {topic} and add to report")
# auto_compact fires automatically when context fills up
```

## When to use

- Long-running agents with many tool calls
- Sessions with large file reads
- Agents running background loops
- Any agent that may exceed context limits

## Events used

| Event | Handler | Purpose |
|-------|---------|---------|
| `after_llm` | `check_and_compact` | Check usage, compact if >= 90% |

## Source

```
connectonion/useful_plugins/auto_compact.py
```
