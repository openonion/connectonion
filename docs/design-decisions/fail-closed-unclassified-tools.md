# Fail Closed for Unclassified Tools

*Date: 2026-08-10*  
*Status: Accepted*

## Context

ConnectOnion can register tools dynamically through plugins and MCP. The tool approval hook previously used `DANGEROUS_TOOLS` as a denylist: a live tool whose name was not in that set skipped approval automatically.

That assumption was valid only while the framework controlled every tool name. A plugin can expose a new name with file, process, network, or external-service effects. Classifying that name as safe merely because core has never seen it turns extensibility into an approval bypass.

## Decision

When an agent has live IO, approval is allowlist-based:

1. Explicit template, config, skill, and user permissions are evaluated first.
2. `auto_approve` auto-approves only the named file-edit tools.
3. `full_access` remains an explicit authority bypass owned by its plugin.
4. Every other tool call must receive operator approval; a hosted non-admin requester is rejected without a dialog.

In a hosted session, only an admin operator may enable `auto_approve` or `full_access`.
Non-admin requesters are normalized to `default`, and the approval hook also
refuses to honor stale elevated mode state as defense in depth.

Local library use without `agent.io` remains non-interactive. `DANGEROUS_TOOLS` remains public compatibility metadata for known effectful tools, but it is no longer the security boundary.

This policy stays inside the approval hook. Tool registration and execution remain separate concerns.

## Consequences

- New plugin and protocol-provided tools cannot silently acquire live side effects.
- Custom read-only tools may prompt once for the operator until they receive a template, config, skill, or session permission.
- Existing standard read-only tools keep their current experience because the host template explicitly permits them.
- co ai grants `codex` and `claude_code` only inside its outer LLM-loop session because those wrappers own inner action approval. This applies to CLI and hosted co-ai sessions but never enters the shared remote-EXEC whitelist. Hosted non-admin Claude delegation is refused; hosted non-admin Codex is read-only with nested approvals denied.
- Non-admin remote requesters fail closed instead of receiving an approval dialog they do not own.
- A remote mode-change frame cannot escalate a requester past that owner gate.
- OIP clients observe future MCP tools through the same deterministic approval boundary.

## Alternatives Rejected

### Expand the denylist

No finite list can classify names introduced after release. Missing one entry recreates the vulnerability.

### Trust tool prefixes or descriptions

Names and descriptions are supplied by extension authors and are not enforceable capabilities. A tool called `read_data` can still write files or use the network.

### Prompt during local no-IO use

There is no approval channel in that mode. Changing it would break ordinary library workflows without adding a usable security decision point.

### Put policy in the executor

Execution should run the already-authorized call. Keeping policy in the approval hook preserves the separation established in [DD-012](012-tool-execution-separation.md).

## Related Decisions

- [DD-012: Tool Execution Separation](012-tool-execution-separation.md)
- [DD-020: Trust System and Network Architecture](020-trust-system-and-network-architecture.md)
- [DD-023: Trust Policy System](023-trust-policy-system-design.md)
