# Session Persistence

## Philosophy: Client Copy, Server-Authoritative Recovery

### Core Principle

The client keeps the latest returned session for rendering, browser refreshes,
and continuation requests. The host also keeps owner-bound recovery snapshots
and server-only capability state. Once a session has a stored owner-bound
snapshot, that server transcript is authoritative; a client-provided higher
iteration or newer timestamp cannot replace it. This also applies when the
stored transcript is empty—an empty server snapshot is state, not a signal to
fall back to client history.

### Design Decision

- **Client session copy**: Browser-side continuity and UI rendering
- **Recovery transcript and final results**: Server-authoritative and bound to the signed owner
- **Capability state**: Server-only and bound to both owner and signed session ID

### Why Keep a Client Session Copy?

1. **Browser Continuity**
   - The latest returned session survives refreshes in localStorage
   - New sessions can be seeded from a signature-bound client snapshot
   - Existing stored sessions resume from the owner-bound server transcript

2. **The UI is Everything**
   - User sees the conversation in their browser
   - That's the reality of the session
   - The client can render without fetching after every UI action

3. **Clear State Boundaries**
   - A client copy round-trips for continuity
   - Recovery transcripts and capability state stay server-side
   - Client-visible plugin state never grants authority

4. **Client Control**
   - User controls their conversation data
   - Clear in browser localStorage
   - Privacy-friendly

### Why Server-Side for Results?

The server saves recovery records for **long-running tasks** and checkpoints
security-sensitive capability progress before privileged work continues:

```
User sends request → Disconnects (browser closed, network issue)
Server continues processing (10 minutes)
Server finishes → Saves result to .co/session_results.jsonl
User comes back → Signs session.get for that ID → Gets result
```

This does not make arbitrary client session fields authoritative. Storage is for:
- Completed task results
- Long-running operations
- Polling recovery when client disconnected
- Owner-bound capability checkpoints (for example, consumed ULW turns)

### Authenticated Recovery Reads

`GET /sessions/{id}` and `GET /sessions` are not anonymous endpoints. An owner
signs a short, action-bound payload and sends the signature in headers:

- `X-From`: the caller's public address
- `X-Signature`: Ed25519 signature over canonical JSON
- `X-Timestamp`: the same numeric timestamp used in the signed payload

For one session, sign
`{"action":"session.get","session_id":"<id>","timestamp":<number>,"to":"<host-address>"}`.
For the owner-scoped list, sign
`{"action":"session.list","timestamp":<number>,"to":"<host-address>"}`.
Canonical JSON uses sorted keys with no extra whitespace. The server reconstructs
`to` from the current host identity, so the request still sends only the three
`X-From`, `X-Signature`, and `X-Timestamp` headers—there is no `X-To` header. A
valid owner signature can only read records whose `owner_address` matches.
Cross-owner and legacy ownerless records return `404`.

An operator may instead send `Authorization: Bearer <OPENONION_API_KEY>` to
read all sessions, including legacy ownerless records. Treat this as an admin
credential, not a client polling mechanism.

### Modern Signed Session Actions

Modern clients bind every session action to the intended host and exact data:

- `session.connect`: signs `to`, `timestamp`, optional `session_id`, and
  `session_sha256`, the SHA-256 of canonical JSON for the supplied session (or
  `{}` when absent).
- `session.input`: signs `to`, `timestamp`, `session_id`, prompt, a unique
  `input_id` (WebSocket) or `request_id` (HTTP), optional mode, and
  `attachments_sha256`.
- `attachments_sha256` hashes canonical JSON shaped as
  `{"images":[...],"files":[...]}`; omitted attachments are empty arrays.

The top-level routing fields must match the signed values. Request IDs are
single-use within the signature window: replaying the same signed INPUT returns
HTTP `409` or a WebSocket `ERROR` with `duplicate request`.

Older INPUT frames without the complete binding can run only as Safe-mode work
for an idle session. They cannot restore capabilities or request a privileged
mode. All INPUT frames received during a running turn are rejected without
claiming their request ID; retry after the current OUTPUT. Resume/migrate a
legacy ownerless record by starting a new session without its old `session_id`.

### Architecture

```
┌─────────────────────────────────┐
│ Client (localStorage)           │
│ - Session state (messages)      │
│ - Conversation context          │
│ - Turn count                    │
│ - Latest client-visible copy    │
└─────────────────────────────────┘
         ↓ sends with request
┌─────────────────────────────────┐
│ Server                          │
│ - Receives session from client  │
│ - Processes with agent          │
│ - Returns updated session       │
│ - Saves owner-bound checkpoints │
│ - Keeps capabilities server-only│
└─────────────────────────────────┘
         ↓ checkpoints + completion
┌─────────────────────────────────┐
│ .co/session_results.jsonl       │
│ - Recovery snapshots/results    │
│ - Server-only capability state  │
│ - For polling recovery          │
│ - Never trusts client authority │
└─────────────────────────────────┘
```

### Server-Side Restore (Whitelist)

When the server receives the client's session, it rebuilds `agent.current_session` from an explicit **key whitelist** — not `dict(session)` — because the incoming session is untrusted client input. The restored keys are `session_id`, `messages`, `trace`, `turn`, and `plugin_state`. Sensitive top-level keys a client might inject (`permissions`, `stop_signal`, capability/bypass flags) are deliberately **not** restored.

For an existing owner-bound session, the persisted server transcript is selected
before this whitelist restore. A client snapshot with a larger `iteration`,
`turn`, or `updated` value does not overwrite stored history. An empty persisted
transcript remains authoritative as well.

`plugin_state` is the generic client-round-tripped slot for non-authoritative
plugin data. A plugin stores under `plugin_state['<name>']`, so core never
hardcodes plugin keys. Because the client can edit this data, it cannot authorize
an action or control a capability lease. Hosted capabilities use separate
server-only state bound to the authenticated caller and session ID; a plugin may
mirror progress into `plugin_state` for display only. See
[Plugins → Persisting Plugin State](concepts/plugins.md#persisting-plugin-state).

### Process Model

The built-in JSONL storage, replay cache, session locks, and active WebSocket
registry are process-local. Run one worker per host identity. `host(...,
workers=N)` rejects `N != 1`; external uvicorn or gunicorn deployments must also
use exactly one worker unless they replace these components with shared,
transactional equivalents and sticky WebSocket routing.

---

## Implementation

### Problem Statement

**Original bug:**
- Session cleared after every successful response
- Browser refresh loses conversation
- Every message starts fresh conversation

**Solution:**
- Keep session during active connection
- Clear session only on explicit reset
- Save to localStorage for browser refresh recovery

### TypeScript SDK Changes

**File:** `connectonion-ts/src/connect.ts`

#### 1. Session Persistence Methods

```typescript
private _saveSession(session: SessionState): void
  // Save full session to localStorage with timestamp
  // Key: 'connectonion_session_{session_id}'

private _loadSession(sessionId: string): SessionState | null
  // Load session from localStorage
  // Returns null if not found

private _loadActiveSessionId(): string | null
  // Get active session_id from localStorage

private _clearSession(sessionId: string): void
  // Clear specific session from localStorage
```

#### 2. Load Session Before INPUT

```typescript
// Try to restore session from localStorage if not in memory
const activeSessionId = this._loadActiveSessionId();
if (activeSessionId && !this._currentSession) {
  const loaded = this._loadSession(activeSessionId);
  if (loaded) {
    this._currentSession = loaded;
  }
}
```

#### 3. Save Session on OUTPUT

```typescript
if (data.session) {
  this._currentSession = data.session;
  this._saveSession(data.session);  // Save for next message
}
```

#### 4. Don't Clear Session on Success (The Bug Fix!)

```typescript
// Before (BUG):
this._clearSessionId();  // Clears after EVERY message!

// After (FIXED):
// Don't clear session - keep for next message in conversation
```

### Behavior Matrix

| Event | Session in Memory | Session in localStorage | Action |
|-------|-------------------|-------------------------|--------|
| First INPUT | None | None | Generate new session_id |
| OUTPUT received | Update | Save with timestamp | Keep for next message |
| Browser refresh | Cleared | Exists | Load from localStorage |
| WebSocket error | Keep | Keep | Allow retry |
| User calls reset() | Clear | Clear | User action |

### When Session is Cleared

**Kept alive:**
- Successful OUTPUT (multi-turn conversations)
- Connection errors (allow retry)
- Connection timeout (allow retry)

**Cleared:**
- User calls `reset()` explicitly

---

## Deployment

### Published Package

**Package:** `connectonion@0.0.9`
**Registry:** https://www.npmjs.com/package/connectonion

### What This Fixes

**Before (Bug):**
```
User: "What is Python?"
Agent: "Python is a programming language..."
  → Session cleared after every message

User: "Tell me more"
  → No context, fresh conversation
Agent: "Tell me more about what?"
```

**After (Fixed):**
```
User: "What is Python?"
Agent: "Python is a programming language..."
  → Session saved and kept alive

User: "Tell me more"
  → Full conversation context
Agent: "Python emphasizes readability and simplicity..."

Connection lost → Retry
  → Session still in localStorage
  → Can continue conversation
```

---

## Design Principles

1. **SDK is simple** - Just save/load/clear, no policy decisions
2. **Client keeps the UI copy** - Existing recovery transcripts remain server-authoritative
3. **Session ID is the flag** - Different conversations = different IDs
4. **Keep sessions alive** - Only clear on explicit user action
5. **Application decides cleanup** - SDK doesn't enforce limits or TTL
6. **Separation of concerns** - SDK persists, application manages

---

## Edge Cases

**Q: What if user clears localStorage?**
A: Conversation resets. Expected behavior - they cleared their data.

**Q: What if user switches devices?**
A: New conversation. Session is local to that browser.

**Q: What if server has a different session state?**
A: The owner-bound server recovery transcript wins. The client should replace
its local copy with session/chat data returned by `CONNECTED` or `OUTPUT`.

**Q: What if I have a legacy ownerless session?**
A: It cannot be claimed by a new identity. Start a new session without the old
`session_id`; an operator can still inspect the old record with admin bearer auth.

---

## Benefits

### For Users

- Browser refresh preserves conversation
- Connection errors don't lose context
- Can retry failed requests with full history
- Multi-turn conversations work correctly

### For Developers

- Simple API - sessions handled automatically
- Flexible - application chooses cleanup policy
- Explicit recovery model - browser copy plus owner-bound server checkpoints
- Type-safe - full TypeScript support
