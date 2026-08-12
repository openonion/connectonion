# DD-044: Approval modes use mainstream product vocabulary

**Status:** Accepted

**Date:** 2026-08-12

**Related:** [030 Generation-scoped Tool Approvals](030-acp-generation-scoped-tool-approvals.md), [031 Session Mode Authority](031-acp-session-mode-authority.md), [039 Authoritative Host Mode Updates](039-authoritative-acp-host-mode-updates.md), [040 Durable Host Mode Transactions](040-durable-acp-host-session-mode-transactions.md), [Issue #903](https://github.com/openonion/connectonion/issues/903)

## Context

ConnectOnion exposed the approval IDs `safe`, `accept_edits`, and `ulw`. Their
behavior was useful, but the names required ConnectOnion-specific explanation
and differed across the Host, `@connectonion/react`, O Chat, ACP, documentation, and
delegated coding tools. O Chat also has a local Plan workflow, which is a
conversation state rather than server approval authority.

## Decision

The canonical approval vocabulary is:

| ID | Display name | Authority |
|---|---|---|
| `default` | Default | Ask before sensitive, unpermitted tool calls. |
| `auto_approve` | Auto-approve | Automatically approve named file-edit tools; retain policy checks for other sensitive tools. |
| `full_access` | Full access (YOLO) | Operator-only approval bypass with the configured autonomous checkpoint. |

Plan remains an O Chat workflow. When Plan talks to the Host, its server
approval authority is `default`. YOLO is a familiar display name and API
shorthand for `full_access`, not a fourth mode.

Host and React serializers emit only canonical values. Compatibility readers may
accept the previous three IDs and their corresponding turn fields, normalize
them immediately, and expose only canonical state to the rest of the system.
New sessions and persisted updates never write the previous vocabulary.

An untrusted presentation reader may omit an unknown value and display Default.
An authority-bearing persisted Host or ACP snapshot with an unknown, malformed,
or over-authorized value is rejected before the Agent runs, as required by
DD-031; “fail closed” does not mean silently rewriting corrupt authority state.

Delegation adapters translate canonical product intent to provider-specific
controls at their boundary. Provider terms do not leak back into the Host
protocol.

Claude's CLI `--safe-mode` is an isolation switch, not the retired product mode
ID `safe`. Delegated runs keep that switch while the ConnectOnion product mode
becomes `default`; renaming the product vocabulary must not re-enable provider
customizations or persistent local allow rules.

## Compatibility and rollback

The compatibility reader is deliberately isolated and covered by migration
tests. It can be removed after one compatibility window. Rolling back the UI is
safe only while the server still has that reader; canonical-only sessions must
not be rewritten with previous IDs.

## Rejected alternatives

- **Keep both vocabularies public:** creates two names for every state and lets
  old IDs continue to spread through persisted data.
- **Treat Plan as server authority:** conflates planning UI with tool approval
  and can leave a session without a valid exit path.
- **Make YOLO a separate protocol ID:** duplicates Full access behavior and
  forces every client to handle a fourth state.
- **Map Auto-approve to every tool:** changes the existing security boundary;
  this decision renames behavior rather than widening it.
