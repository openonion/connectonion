# DD-048: Carry browser attachments as bounded ACP content blocks

**Status:** Accepted

**Date:** 2026-08-13

**Related:** [DD-029 Persistent ACP Session Ownership](029-acp-persistent-session-ownership.md), [DD-033 ACP stdio MCP Authority](033-acp-stdio-mcp-authority.md), [DD-045 Authenticated ACP WebSocket Gateway](045-authenticated-acp-websocket-gateway.md), [DD-047 Network ACP Virtual Workspace](047-network-acp-virtual-workspace.md), [Issue #919](https://github.com/openonion/connectonion/issues/919)

## Context

O Chat already sends text, images, and files through `@connectonion/react`.
The native ACP adapter accepted only text and resource links. Selecting native
ACP in React would therefore reject an input that the legacy Host supports, or
invite the client to drop content silently. ACP defines image and embedded
resource prompt blocks and an Agent capability for each.

Network attachment data is also an authority boundary. A URI, filename,
MIME type, or `_meta` value supplied by a browser must not select a Host path,
trigger a server-side fetch, expand the virtual workspace, or bypass the Host's
resource limits.

## Decision

The shared ACP adapter advertises `promptCapabilities.image=true` and
`embeddedContext=true`. It accepts:

- the bounded raster MIME set already supported by ConnectOnion's image path:
  PNG, JPEG, GIF, and WebP;
- embedded text and base64 blob resources whose URI has the exact form
  `connectonion-upload:/<percent-encoded-filename>`.

The upload URI is an opaque name carrier. It has no authority outside this
prompt. It has no host, query, fragment, nested path, slash, backslash, dot
segment, or NUL, and its UTF-8 filename is bounded to one filesystem component.
No resource link is fetched. A resource link remains descriptive prompt text.
Audio remains unsupported and is not advertised.

The adapter validates count, MIME syntax, base64 form, and decoded size before
opening an Agent turn. It then calls the existing
`Agent.input(..., images=..., files=...)` path exactly once. The Host's
configured `max_file_size` and `max_files_per_request` values are captured at
startup and bound to every authenticated ACP adapter. The gateway's smaller
one-MiB JSON-RPC message limit remains a separate outer resource boundary; this
decision does not enlarge it to fit the legacy ten-MiB inline default.

Files are written only by the existing Agent upload implementation after the
ACP request has passed validation. Network files are staged beneath the same
authenticated-principal namespace that owns their durable ACP sessions; local
stdio keeps its existing Agent upload root. A cancelled, refused, or failed
prompt removes files created by that uncommitted turn before restoring the
last-good ACP snapshot. A successful commit retains them. File paths remain
internal Agent context and are never returned as network workspace authority.

## Consequences

- React can preserve the browser's typed attachment API while using official
  ACP content models; O Chat does not parse ACP.
- Invalid content fails before session mutation, Agent input, or file writes.
- Native inline attachments are practically bounded by the ACP frame limit;
  larger files require a separately designed authenticated streaming upload.
- Existing stdio ACP clients gain the same declared content support without a
  second prompt parser.

## Rejected alternatives

- **Put attachments in `_meta`:** metadata is extensible description, not an
  authority or content channel.
- **Use `file://` or arbitrary URIs:** they could name Host files or create
  SSRF if fetched.
- **Treat every image MIME as safe:** SVG and future active formats have a
  different rendering/security surface from the existing raster path.
- **Silently drop unsupported blocks:** the user would believe the Agent saw
  content it never received.
- **Raise the WebSocket frame limit to the legacy upload default:** one large
  buffered JSON frame expands the gateway's reviewed memory boundary. A future
  streaming design should solve large files explicitly.
