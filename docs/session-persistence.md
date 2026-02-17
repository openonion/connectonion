# Session Persistence

## Philosophy: Client-Side as Source of Truth

### Core Principle

**The UI is everything.** What you see is what actually is. We don't want unexpected state mismatches between client and server.

### Design Decision

- **Session State (conversation)**: Client-side is source of truth
- **Final Results (completed tasks)**: Server-side for polling recovery

### Why Client-Side for Session State?

1. **No State Synchronization Problems**
   - Server storing session = two sources of truth
   - Client localStorage + Server disk = potential conflicts
   - Solution: Only one source of truth (client)

2. **The UI is Everything**
   - User sees the conversation in their browser
   - That's the reality of the session
   - Server doesn't need to "remember" conversations

3. **Simplicity and Elegance**
   - Server stays stateless
   - No disk I/O on every request
   - Scales infinitely

4. **Client Control**
   - User controls their conversation data
   - Clear in browser localStorage
   - Privacy-friendly

### Why Server-Side for Results?

The **only** reason server saves anything is for **long-running tasks**:

```
User sends request → Disconnects (browser closed, network issue)
Server continues processing (10 minutes)
Server finishes → Saves result to .co/session_results.jsonl
User comes back → Polls /sessions/{id} → Gets result
```

This is **NOT** for conversation state. It's only for:
- Completed task results
- Long-running operations
- Polling recovery when client disconnected

### Architecture

```
┌─────────────────────────────────┐
│ Client (localStorage)           │
│ - Session state (messages)      │
│ - Conversation context          │
│ - Turn count                    │
│ ✓ SOURCE OF TRUTH               │
└─────────────────────────────────┘
         ↓ sends with request
┌─────────────────────────────────┐
│ Server (stateless)              │
│ - Receives session from client  │
│ - Processes with agent          │
│ - Returns updated session       │
│ - Does NOT save to disk         │
└─────────────────────────────────┘
         ↓ only on completion
┌─────────────────────────────────┐
│ .co/session_results.jsonl       │
│ - Final results only            │
│ - For polling recovery          │
│ - NOT for conversation state    │
└─────────────────────────────────┘
```

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
2. **Client is source of truth** - Session in localStorage, not server disk
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
A: Impossible - server doesn't store session state, only final results.

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
- Stateless server - no server-side session storage needed
- Type-safe - full TypeScript support
