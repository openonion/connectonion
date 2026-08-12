# ACP Agent

Delegate one coding turn to an ACP-speaking child agent while keeping the outer
ConnectOnion conversation in charge.

```python
from connectonion import Agent
from connectonion.useful_tools import acp_agent

agent = Agent("lead", tools=[acp_agent])
agent.input("Ask Codex to inspect the failing tests")
```

Named engines are `claude-code`, `codex`, and `gemini`. Claude Code and Codex
use exact-version ACP adapters; Gemini uses its native experimental ACP mode.
The existing `claude_code` and `codex` tools remain available and are still the
preferred engine-specific paths.

Every result is a JSON envelope:

```json
{
  "engine": "codex",
  "session_id": "...",
  "resumed": false,
  "stop_reason": "end_turn",
  "result": "..."
}
```

Pass the returned `session_id` to resume the same engine session. A failed
resume returns an error; it never silently starts a different conversation.

## Permissions

The public tool uses manual approval. A model can choose only a named engine;
it cannot provide a process command or change the approval policy. Operators
can bind a different policy before registering the tool:

```python
from connectonion import Agent
from connectonion.useful_tools import ACPAgent

read_only = ACPAgent(approval="deny", workspace="./my-project")
agent = Agent("reviewer", tools=[read_only])
```

`manual` asks the local operator through a revocable tool IO lease and fails
closed without that approval channel or for a hosted non-admin requester. Its
approval is one-shot and remains inside the turn timeout. `deny` refuses
permission requests. `auto` allows requests inside the named adapter's
configured workspace mode; it is intended only for an operator-selected,
isolated workspace.

The process working directory at `ACPAgent` construction becomes its default
launch root. An operator can bind a narrower root with
`ACPAgent(workspace=...)`. The model may choose that directory or a descendant
through `cwd`; resolved paths outside it, including symlink escapes, fail
closed.

This is a working-directory boundary, not a portable operating-system sandbox.
Codex applies its own sandbox mode. Claude Code and Gemini apply their reported
permission modes, but read-like actions can be pre-approved by an engine. Run
untrusted child tasks in a container or OS sandbox when filesystem containment
is required.

## Visible child activity

The tool streams bounded child tool start/completion cards with stable IDs.
Normal progress cards omit raw inputs and outputs; a manual approval card gets
a bounded input preview. The final result is capped at 64 KiB.

Child ACP thoughts and plans are deliberately not published as outer session
thoughts or plans. Their privacy and ownership differ from ConnectOnion's
persisted application thoughts and canonical TodoList state.

## Readiness

`engine_status()` reports the exact adapter version, launcher availability, and
a clearly labelled credential-file presence hint. It does not claim that a
credential is valid or that a provider call will succeed.

The named Claude Code and Codex routes require `npx` and their normal local CLI
authentication. The first run may download the exact pinned adapter version.
Gemini CLI exposes native ACP modes, but its provider/account availability is
version- and account-dependent; `engine_status()` is only a local readiness
hint, not a successful provider smoke test.
