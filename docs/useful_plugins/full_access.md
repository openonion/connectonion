# Full access

Full access is ConnectOnion's bounded approval-bypass mode. It changes whether
routine tool calls ask; it does not decide what work to do and never starts
another Agent turn.

## Usage

```python
from connectonion import Agent
from connectonion.useful_plugins import (
    enable_full_access,
    full_access,
    tool_approval,
)

agent = Agent("worker", plugins=[tool_approval, full_access])
enable_full_access(agent, turns=10)
agent.input("Refactor the codebase")
```

For `co ai`:

```bash
co ai --full-access "Fix the failing tests" --full-access-turns 10
```

## Behavior

The public state has exactly two fields:

```json
{"mode": "full-access", "turns_left": 10}
```

Each completed user-driven turn decrements `turns_left`. At zero, the canonical
state atomically becomes `{"mode": "auto"}`. Full access never synthesizes a
prompt, recursively calls `agent.input(...)`, extends its own grant, or infers
that an objective is unfinished.

The Host offers Full access only when it was launched with a positive ceiling.
Every authenticated participant sees the same ordinary session modes; admin
control-plane authorization is separate. A client can select `full-access`, but
cannot provide or increase `turns_left`.

Only `read-only`, `auto`, and `full-access` are accepted. Old labels and fields
are discarded to Auto and never translated into authority.

## Source

`connectonion/useful_plugins/full_access.py`
