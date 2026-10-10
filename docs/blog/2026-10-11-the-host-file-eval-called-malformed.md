---
description: A running Host's agent.py was refused by co eval as malformed, because its host(create_agent) call sits under __main__. Eval now falls back to the create_agent factory.
tags: [Eval, Benchmarks]
---

# The Host file eval called malformed

A team running a guest-reply agent wanted to benchmark it. Their `agent.py`
was the shape we recommend for a Host, and it was serving real
conversations:

```python
def create_agent() -> Agent:
    ...

if __name__ == "__main__":
    host(create_agent)
```

`co benchmark check` passed. Then `co eval run ... --agent agent.py` exited
before running a single case:

```
could not load an Agent from agent.py: No 'agent' instance found ...
Structure your file like this: agent = Agent(...)
```

The file worked. Eval just couldn't see that it did.

## Why eval missed it

Eval has to load an Agent from a file without starting a server. It does
this by importing the file with `host()` swapped for a stub that records
whatever it was given. That handles our own `co create` template, which
calls `host(lambda: create_agent(...))` at module level. It also handles a
plain `agent = Agent(...)`.

This file's `host()` call is under `if __name__ == "__main__"`. On import,
`__name__` is `agent_module`, so the call never runs and the stub records
nothing. Eval found no `agent` and nothing hosted, and told the user to
restructure a file that had nothing wrong with it. To work around it, they
wrote a wrapper module that called the factory at import time.

## The fallback

When there is no module-level `agent` and nothing was passed to `host()`,
eval now calls the file's `create_agent()` if it has one. That is the name
the `co create` template uses and the name the issue reported. Calling it
builds an Agent the same way the Host would for a new conversation, and it
opens no listener. The error for a file that really has no Agent now lists
the factory shape as a valid choice.

The new test writes exactly the file from the report, with the factory and
`host()` under `__main__`, and loads it. It failed on main with the old
error and passes now.
