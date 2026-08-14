# ACP Agent

Delegate one coding turn to an ACP-speaking child agent while keeping the outer
ConnectOnion conversation in charge.

```python
from connectonion import Agent
from connectonion.useful_tools import acp_agent

agent = Agent("lead", tools=[acp_agent])
agent.input("Ask Claude Code over ACP to inspect the failing tests")
```

Named engines are `claude-code`, `codex`, and `gemini`. Claude Code and Codex
use exact-version ACP adapters; Gemini uses exact `@google/gemini-cli@0.55.1`
through its current native `--acp` mode.
The existing `claude_code` and `codex` tools remain available and are still the
preferred engine-specific paths.

| Engine | Supported approval policies | Cross-process resume |
|---|---|---|
| `claude-code` | `manual`, `auto`, `deny` | yes |
| `codex` | explicit operator-selected `auto` only | yes |
| `gemini` | `manual`, `auto`, `deny` | no at pinned `0.55.1` |

[Google stopped serving Gemini CLI requests](https://github.com/google-gemini/gemini-cli/discussions/28017)
for free, Pro, and Ultra individual OAuth accounts on June 18, 2026. The named
Gemini route therefore requires a Gemini API key, Vertex AI, or an enterprise
Code Assist account. A legacy `~/.gemini/oauth_creds.json` file is not treated
as proof of readiness.

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

For Claude Code and Codex, pass the returned `session_id` to resume the same
engine session. A failed resume returns an error; it never silently starts a
different conversation. Real conformance testing found that Gemini CLI 0.55.1
does not persist its advertised ACP session across these one-process-per-turn
invocations. A named Gemini turn therefore returns an empty `session_id`, and
supplying one fails before launch instead of pretending to resume.

For custom ACP agents, continuation follows the capabilities returned by
`initialize`. The client prefers `sessionCapabilities.resume` because it does
not need transcript replay, and otherwise uses `loadSession` for compatibility.
It sends exactly one selected lifecycle request; a failure never triggers a
fallback request through the other method. An explicitly null
`agentCapabilities` value means that no optional capability was advertised, so
continuation fails with the same capability error before sending a lifecycle
request. The legacy `loadSession` flag must be a JSON boolean or null; strings
and numbers fail initialization instead of being coerced into a capability.

This adapter implements ACP protocol major version 1. The initialize response
must carry `protocolVersion` as a JSON integer, not a string or boolean. An
invalid type or different major closes the child before creating or resuming a
session.

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

`codex-acp@1.1.14` is deliberately stricter at the ConnectOnion boundary than
its own mode list suggests. Its `read-only` mode supplies Codex's `on-request`
approval policy, which can execute shell and outbound network actions without
an ACP permission callback. ConnectOnion therefore rejects named Codex ACP
launches under `manual` or `deny` before starting the adapter. Use the native
`codex` tool for approval-aware work. An operator who explicitly wants the
generic Codex ACP route must construct `ACPAgent(approval="auto", ...)` and run
it in an appropriately isolated workspace.

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
a bounded input preview. If the child emits multiple ACP messages during one
turn, startup notices remain separate and only the last `messageId` becomes the
result. The final result is capped at 64 KiB.

Child ACP thoughts and plans are deliberately not published as outer session
thoughts or plans. Their privacy and ownership differ from ConnectOnion's
persisted application thoughts and canonical TodoList state.

## Readiness

`engine_status()` reports the exact adapter version, launcher availability,
supported authentication choices, a conservatively labelled credential-file
hint, and each engine's `supported_approval_modes` and `supports_resume`
capability. It does not claim that a credential is valid or that a provider call
will succeed. Gemini intentionally reports no generic credential-file hint,
because an individual OAuth file can exist after that account path has been
retired.

The named Claude Code, Codex, and Gemini routes require `npx` and their normal
local CLI authentication. The first run may download the exact pinned package.
Child processes inherit the ACP SDK's trimmed HOME/PATH/shell baseline, not the
entire parent environment. Claude additionally receives only an explicitly set
`CLAUDE_CONFIG_DIR` or `ANTHROPIC_API_KEY`; Codex receives only its selected API
key or `CODEX_HOME`; Gemini receives only explicitly configured Gemini API-key
or Vertex authentication variables and cannot open a browser login from a
child turn. Unrelated ambient secrets are not forwarded. Gemini CLI exposes
native ACP modes, but its provider/account availability is version- and
account-dependent. Individual OAuth is no longer served; API-key, Vertex, and
enterprise Code Assist remain the supported routes. `engine_status()` is only a
local readiness hint, not a successful provider smoke test.

## `co ai`

`co ai` registers `acp_agent` with the same operator-owned boundary as its
native coding tools. Read only and Workspace profiles use inner `manual`; only
a valid, bounded Full Access grant maps to `auto`. Hosted non-admin requesters
cannot launch a local ACP child process. Because ordinary profiles cannot
safely select the current Codex ACP adapter, use `codex` there and keep
`acp_agent` for Claude Code, Gemini, or another reviewed ACP integration.
