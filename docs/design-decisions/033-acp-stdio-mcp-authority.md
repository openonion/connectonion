# DD-033: ACP stdio MCP servers require explicit launch authority

**Status:** Accepted

**Date:** 2026-08-10

## Context

ACP session creation and resume can supply MCP server launch commands,
arguments, and environment variables. Supporting those servers makes ACP more
useful, but it also turns a protocol request into local process execution.
Treating `mcpServers` as ordinary session metadata would let any connected ACP
client start arbitrary binaries with the agent process's credentials.

The [ACP session setup specification](https://agentclientprotocol.com/protocol/v1/session-setup)
requires agents to support stdio MCP servers. The
[MCP tools specification](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2026-07-28/server/tools.mdx)
also says tool annotations are untrusted and recommends human confirmation,
timeouts, and result validation. These requirements must fit ConnectOnion's
existing session ownership and approval decisions rather than creating a
second policy system.

## Decision

### Require a launch-time authority ceiling

`co ai --acp` rejects every non-empty `mcpServers` list before spawning a
process. The operator must start `co ai --acp --acp-mcp` to let the ACP client
request session-scoped stdio servers. The flag is an authority ceiling, not an
automatic tool grant.

Only ACP stdio entries are accepted. HTTP, SSE, ACP-transport MCP, resources,
prompts, sampling, and elicitation remain out of scope. Commands must be
absolute. Server names, arguments, environment entries, schemas, pagination,
tool counts, calls, and results all have explicit bounds. The complete launch
set is validated before the first process starts.

### Keep process ownership inside one session task

Each session owns one MCP pool. A dedicated asyncio task enters every official
SDK context, discovers tools, serializes calls, and exits those contexts in the
same task. This avoids crossing AnyIO cancel-scope ownership boundaries.
Partial startup closes already-started servers. `session/close`, EOF,
construction failure, and quarantined ACP state all close the pool and reap its
processes before releasing durable session ownership.

Resume reconnects only the full `mcpServers` list supplied by that resume
request. Commands, arguments, environment values, and discovered tools are not
persisted in ConnectOnion snapshots.

The child runs in the ACP session cwd. The MCP SDK supplies its small safe
environment baseline and ConnectOnion overlays only the ACP entry's explicit
environment. The agent's complete parent environment is never copied.

### Export ordinary, fail-closed ConnectOnion tools

Remote names map to stable bounded names of the form
`mcp__<server-slug_hash>__<tool-slug_hash>`. Readable slugs help review while
short SHA-256 suffixes disambiguate servers and tools. Registration refuses any
remaining collision.

MCP annotations never grant authority. Exported MCP callables enter the normal
ConnectOnion tool registry and the fail-closed policy established by DD-030 and
the unclassified-tool decision. Default and Auto-approve modes request ACP
operator permission before an MCP side effect. Only explicit Full access authority can
bypass that prompt.

An MCP "allow for this session" grant is scoped to the exact live MCP pool.
Client-granted `mcp__...` permission entries are removed from durable snapshots
while remaining available to later prompts in the current open runtime. Resume
must therefore request approval again, even when a new launch exports the same
server and tool names. Explicit operator permissions from `.co/host.yaml`
remain configured. This is narrower than DD-030's ordinary durable session
approval because MCP launch identity and secrets are intentionally not stored.

Calls are cooperatively cancellable, have a 60-second SDK read timeout, and
accept and return at most 64 KiB of validated JSON. Discovery accepts at most 8
servers, 128 tools, 32 pages, and 64 KiB per input schema.

### Use the stable MCP SDK major

The runtime dependency is `mcp>=2.0.0,<3`. The lower bound is the first stable
v2 API used by this adapter; the upper bound prevents an unreviewed major API
change. Real stdio tests exercise official v2 client and server code, process
cleanup, safe environment inheritance, resume, and approval-before-side-effect.

## Consequences

- An ACP connection alone cannot obtain local process-launch authority.
- MCP tools reuse one reviewable approval boundary instead of trusting remote
  names, descriptions, or annotations.
- Secrets in the parent process environment are absent unless the ACP client
  explicitly supplies them for that server.
- Reconnecting a session requires the client to resend its MCP configuration.
- Reconnecting never inherits an earlier MCP process's session approval.
- Slow or oversized third-party tools fail within a bounded surface.
- HTTP and richer MCP capabilities require later design decisions.

## Rejected alternatives

- **Enable MCP whenever ACP is enabled:** silently expands protocol access into
  arbitrary local process execution.
- **Copy the full parent environment:** exposes unrelated credentials to every
  third-party server.
- **Persist launch configuration:** writes commands and secrets into durable
  agent state and lets resume reuse stale authority.
- **Trust MCP annotations or read-like names:** remote metadata is descriptive,
  not an enforceable capability.
- **Keep SDK contexts in request handlers:** session close can run in another
  task, violating the SDK's AnyIO ownership boundary.
- **Support every MCP transport now:** enlarges authentication, networking, and
  lifecycle scope before the mandatory stdio path is proven.

## Related decisions

- DD-025: Interruptible agent steps
- DD-029: Persistent ACP session ownership
- DD-030: Generation-scoped ACP tool approvals
- DD-031: ACP session mode authority
- DD-032: ACP interoperability evidence
- Fail Closed for Unclassified Tools
