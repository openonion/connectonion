# A Session ID Is Not a Work Room

The first Claude Code browser test appeared to pass. O Chat showed a
`claude_code` tool card, the tool ran for six seconds, and the assistant returned
the requested text. Expanding the card revealed an even stronger signal: a real
Claude provider envelope with `status: completed`, `exit_code: 0`, and a UUID
session ID.

There was still no **Open Work Room** button.

The temptation was to fix that in React. The browser had the tool name and the
JSON result, so it could parse the envelope, recognize `claude_code`, manufacture
a provider card, and infer which later calls belonged to it. That would make one
screenshot look right. It would also put protocol reconstruction in the least
authoritative layer.

Codex showed the intended boundary. `co ai` installed `CodexPlugin`, which owns a
provider invocation from start to finish. It emits a stable invocation ID, the
parent tool-call ID, provider name, permission mode, terminal status, elapsed
time, result, error, and resumable session ID. Child commands carry the same
correlation. React normalizes those events, and O Chat only presents them.

Claude had all the difficult pieces — a bounded streaming reader, structured
results, cancellation, nested tool activity, and session resume — but `co ai`
registered it as a plain function. The streaming reader could correlate child
activity with the outer tool call. No owner existed to emit the parent provider
lifecycle, so the browser correctly rendered the only contract it received: a
generic tool card.

The fix was not a Claude-shaped frontend exception. `co ai` now installs
`ClaudeCodePlugin` beside `CodexPlugin`. Both adapters emit the same provider
lifecycle while keeping their provider-specific transports and policies. The
model-visible Claude signature remains `prompt`, explicit `cwd`, optional
`session_id`, model, and timeout. OIP still carries normalized events rather
than provider CLI output.

That symmetry could not weaken the hosted security boundary. Claude's `plan`
mode is provider behavior, not a process sandbox, so an invited contact still
cannot start the operator's local Claude CLI. The plugin checks the
signature-verified requester before resolving `cwd`; a non-admin therefore
cannot launch Claude or probe operator paths. An admin's Read only, workspace,
or bounded Full access choice maps to Claude manual, Accept Edits, or Auto mode.
The browser never chooses those modes, and resuming reapplies the current Host
ceiling.

The acceptance test measured the whole path, not just the presence of a button.
A real admin browser sent one OIP request through the production relay. The card
rendered **Claude Code · Completed · Open Work Room**. Opening the room showed the
provider UUID as its target. A follow-up typed inside that room reached the same
outer OIP session, caused `co ai` to call Claude with that exact UUID, and returned
the second requested result. Ninety focused unit and security tests passed before
the browser run.

The lesson is the same one that makes protocol adapters worth having: data being
available is not the same as semantics being owned. A session ID inside an
opaque result can be displayed. A Work Room needs a lifecycle — identity,
parentage, status, authority, continuation, and replay — emitted by the layer
that actually controls the provider.

