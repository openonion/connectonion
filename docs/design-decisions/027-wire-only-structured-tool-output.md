# Design Decision: Stream Structured Tool Output Without Persisting It

**Status:** Accepted
**Date:** 2026-08-10
**Related:** [012 Tool Execution Separation](012-tool-execution-separation.md), [017 Session Logging and Eval Format](017-session-logging-and-eval-format.md), [026 Structured Turn Outcomes](026-structured-turn-outcomes.md)

## Decision

A successful tool result may add a detached JSON-native `raw_output` value to
its streamed `tool_result` event. The canonical trace entry, session snapshot,
LLM tool message, logger, and console keep the existing string `result` only.
Protocol adapters may map the internal snake-case field to their wire schema,
including OIP tool-result payloads.

Tool execution builds the structured value because it alone still owns the
original Python return value. `Agent._record_trace` accepts optional wire-only
fields and creates a separate top-level event for transport after appending the
canonical entry. Both representations share one event ID and timestamp. The
following `session_sync` contains only canonical state.

The accepted tree is deliberately narrow: null, exact booleans, integers,
finite floats, strings, lists, and dictionaries with exact string keys. It is
rebuilt recursively with a maximum container depth of 8 and a maximum compact
UTF-8 JSON size of 64 KiB. Cycles, non-finite floats, bytes, Paths, tuples,
non-string keys, custom objects, oversized values, and any mixed tree that
contains them omit `raw_output` and use the existing string result.

## Why

JSON-native results are useful to protocol clients, but adding arbitrary Python
objects to the trace would weaken the trace's JSON-compatible persistence
contract. Appending a raw value and deleting it after send would also be racy:
host transports can encode entries concurrently.

A bounded detached wire copy keeps the persisted source of truth stable while
allowing clients to preserve structure. Keeping the structured value on the
same event preserves tool-result ordering without a second correlation path.

## Security boundary

This is not a redaction layer. Tool authors remain responsible for the content
they return, as they are for today's string result. The runtime never
introspects custom attributes, invokes model serializers, pickles objects, or
implicitly decodes bytes. Error results do not receive structured output.
Depth and byte limits bound the additional serialization work and payload.

## Rejected alternatives

- **Persist the structured value:** expands snapshot compatibility and secret
  exposure for data needed only by live protocol clients.
- **Append then delete:** races asynchronous session forwarding.
- **Use `json.dumps(default=str)`:** silently invokes arbitrary object string
  conversion and misrepresents non-JSON values as structured data.
- **Support Pydantic or dataclasses automatically:** introspection and custom
  serializers create a much broader execution and disclosure surface.
- **Send a second raw-result event:** adds ordering and correlation complexity.
