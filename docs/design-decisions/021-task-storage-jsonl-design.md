# Task Storage: Why JSON Lines with TTL Expiry

*December 2025*

When designing `host()`, we needed to store task results so clients can fetch them later if connections drop. This document explores all the options we considered and explains why we chose JSON Lines with TTL expiry.

---

## The Problem

When an agent is hosted, tasks need to be persisted:

```
Client                                    Agent
   │                                        │
   │── POST /input ────────────────────────▶│
   │◀─ {task_id: "abc"} ───────────────────│
   │                                        │
   │   (connection drops during long task)  │
   │                                        │
   │── GET /tasks/abc ─────────────────────▶│
   │◀─ {result: "..."} ────────────────────│  ← Need stored result
```

Requirements:
1. **Human readable** - Developers should be able to inspect tasks directly
2. **Concurrent safe** - Multiple workers may write simultaneously
3. **Simple** - No external dependencies, easy to understand
4. **Cleanable** - Old tasks should be removed automatically

---

## Part I: Where to Store?

### Option A: Central Server (Our Relay)

```
Client                     Our Relay                    Agent
   │                           │                          │
   │── INPUT ─────────────────▶│── INPUT ────────────────▶│
   │◀─ {task_id} ──────────────│                          │
   │                           │◀─ OUTPUT ────────────────│
   │   (client disconnects)    │   (relay stores result)  │
   │                           │                          │
   │── GET /tasks/abc ────────▶│                          │
   │◀─ {result} ───────────────│                          │
```

**Pros:**
- Simple for developers
- Client can disconnect/reconnect
- Works across devices

**Cons:**
- Privacy concern (we see all data)
- Single point of failure
- Costs us money (storage, bandwidth)
- Vendor lock-in

**Why not chosen:** Privacy and centralization concerns.

---

### Option B: IPFS (Decentralized)

```
Agent: encrypt(result) → IPFS → CID
Client: IPFS.get(CID) → decrypt → result
```

**Pros:**
- Decentralized, no central server
- Content-addressed (verifiable)
- Privacy via encryption

**Cons:**
- Someone must pay for pinning
- IPFS without pinning = data disappears
- Pinning services cost $0.01-0.15/GB/month
- Adds complexity (IPFS dependency)
- Overkill for most use cases

**Who pays for IPFS?**

| Option | Cost | Persistence |
|--------|------|-------------|
| Free tier | $0 | Garbage collected |
| Pin yourself | Electricity + disk | While node runs |
| Pinning service | $0.01-0.15/GB/month | While you pay |
| Filecoin | ~$0.0001/GB/month | Contract duration |

**Why not chosen:** Doesn't solve payment problem, adds complexity. "IPFS sounds good but doesn't change economics."

---

### Option C: Webhook/Callback

```
Client                                    Agent
   │                                        │
   │── INPUT + callback_url ───────────────▶│
   │◀─ "accepted" ─────────────────────────│
   │                                        │
   │   (client goes offline)                │
   │                                        │
   │◀── POST result to callback_url ────────│
```

**Pros:**
- No storage needed
- Fire and forget
- Scales well

**Cons:**
- Client needs public endpoint
- Firewall/NAT issues
- More complex client setup

**Why not chosen:** Requires client to have public endpoint. Most developers don't.

---

### Option D: Email Model

```
Client: "Do this task"
Agent: "I'll email you when done"
       ... works ...
Agent: → sends notification/email with result
```

**Pros:**
- Familiar mental model
- No connection needed
- Different channel

**Cons:**
- Requires email/notification setup
- Different from API pattern
- Complex integration

**Why not chosen:** Too different from standard API patterns. Adds notification complexity.

---

### Option E: Agent Calls Back (Role Reversal)

```
Client: "Do this, reply to 0xMyAddress when done"
Agent: ... works ...
Agent: → initiates connection TO client with result
```

**Pros:**
- Like how phones/humans work
- No storage needed

**Cons:**
- Client must be online to receive
- NAT/firewall issues
- Role reversal adds complexity

**Why not chosen:** Client might not be online. NAT traversal is hard.

---

### Option F: Encrypted Central Storage

```
Agent: encrypt(result, client_pubkey) → store on relay
Client: fetch → decrypt with private_key → result
```

**Pros:**
- Privacy preserved (relay can't read)
- Simple for developers
- Uses existing keypair

**Cons:**
- Still centralized (relay as encrypted mailbox)
- Durov/Dorsey would say: "What if relay goes down?"
- Vendor lock-in

**What would industry leaders say?**

| Person | Concern |
|--------|---------|
| Pavel Durov (Telegram) | "Encryption good, but why central relay?" |
| Jack Dorsey (Twitter) | "Protocol, not platform. Multiple relays." |
| Vitalik Buterin (Ethereum) | "Where's the trustlessness? Who verifies?" |
| Juan Benet (IPFS) | "Content addressing solves this." |

**Why not chosen:** For MVP, we decided to keep it simple with local storage. Encrypted central storage could be added later as optional feature.

---

### Option G: Don't Store At All

Most tasks complete in seconds. Is storage really needed?

```
95% of tasks: < 30 seconds, WebSocket stays open → no storage needed
5% of tasks: Maybe longer
```

**Consideration:** Build for the 95%. Document the limitation.

**Why not fully chosen:** Connection drops do happen. Simple local storage is low-cost insurance.

---

### Option H: Local Storage on Agent (Chosen)

```
Agent stores results locally in ~/.connectonion/tasks.jsonl
Client fetches via GET /tasks/{task_id}
```

**Pros:**
- Privacy (data stays with agent)
- No central dependency
- Agent controls retention
- Simple, no external services

**Cons:**
- Agent must be online to retrieve
- No cross-device without relay

**Why chosen:** Simplest solution that works. Privacy by default. No external dependencies.

---

## Part II: How to Store Locally?

### Option 1: CSV

```csv
task_id,prompt,status,result,created
550e8400,Translate hello,done,Hola,1702234567
```

**Problems:**
- **Not human readable** - Hard to read with long content
- **Race conditions** - Concurrent writes corrupt data (read-modify-write pattern)
- **Parsing issues** - Commas and newlines in results break CSV

**Why not chosen:** Not readable, not concurrent-safe.

---

### Option 2: One JSON File Per Task

```
~/.connectonion/tasks/
├── 550e8400.json
├── 7c4dff69.json
└── 3d4017c3.json
```

**Problems:**
- Thousands of files = slow to list (`GET /tasks`)
- Can't query without reading all files
- File system overhead

**Why not chosen:** Doesn't scale for listing/querying.

---

### Option 3: SQLite

```sql
SELECT * FROM tasks WHERE task_id = '550e8400';
```

**Pros:**
- Handles concurrency
- Good for queries

**Cons:**
- **Binary file** - Users can't `cat` or `grep` it
- Requires SQLite CLI knowledge
- Overkill for simple storage

**Why not chosen:** Not human readable. "Users can't directly read the SQLite file."

---

### Option 4: JSON Lines (Chosen)

```jsonl
{"task_id":"550e8400","status":"running","created":1702234567,"expires":1702320967}
{"task_id":"550e8400","status":"done","result":"Hola","created":1702234567,"expires":1702320967}
```

**Benefits:**
- Human readable: `cat tasks.jsonl`
- Queryable: `grep "550e8400" tasks.jsonl`
- Single file: easy to manage
- Append-only: concurrent safe

---

## Part III: Why Append-Only is Concurrent Safe

### CSV/SQLite: Read-Modify-Write (Unsafe)

```
Worker 1: Read file         → [abc:running, def:running]
Worker 2: Read file         → [abc:running, def:running]
Worker 1: Update abc=done   → [abc:done, def:running]
Worker 2: Update def=done   → [abc:running, def:done]
Worker 1: Write file
Worker 2: Write file        ← Overwrites Worker 1! Data lost!
```

### JSON Lines: Append-Only (Safe)

```
Worker 1: Append line → {"task_id":"abc","status":"done"}
Worker 2: Append line → {"task_id":"def","status":"done"}

Both succeed. No data loss.
```

**Why?** On POSIX systems, append operations are atomic for small writes.

To get current state: find the **last** line for that task_id.

```bash
grep "550e8400" tasks.jsonl | tail -1
```

This is the same pattern used by:
- Kafka (append-only log)
- Git (append-only objects)
- Database WAL (Write-Ahead Log)
- Blockchain (append-only chain)

---

## Part IV: How to Cleanup?

### Option A: File Locking

```python
def cleanup():
    with file_lock:
        # Read all, filter, write back
```

**Problems:**
- Workers wait during cleanup (slow)
- Deadlock risk if process crashes
- Complex error handling

**Why not chosen:** Too complex, risk of deadlocks.

---

### Option B: Log Rotation

```
tasks.jsonl          ← Current
tasks.20241210.jsonl ← Yesterday
tasks.20241209.jsonl ← 2 days ago
```

**Problems:**
- Need to read multiple files for recent tasks
- Date-based, not task-based control
- More complex file management

**Why not chosen:** More complex, less flexible.

---

### Option C: TTL Expiry (Chosen)

Each task has an `expires` timestamp:

```json
{"task_id":"abc","status":"done","result":"...","expires":1702320967}
```

Cleanup logic:
- If `expires < now` AND `status != "running"` → safe to delete
- Running tasks never deleted (even if expired)

```python
def cleanup():
    now = time.time()
    active = []
    for line in open("tasks.jsonl"):
        task = json.loads(line)
        if task["expires"] > now or task["status"] == "running":
            active.append(line)

    # Atomic write
    with open("tasks.jsonl.tmp", "w") as f:
        f.writelines(active)
    os.rename("tasks.jsonl.tmp", "tasks.jsonl")
```

**Why chosen:**
- Per-task control (different TTLs possible)
- Running tasks protected
- Simple logic: expired = safe to delete
- Client had N hours to fetch result

---

## The Final Design

### Storage

```
.co/tasks.jsonl
```

Stored in project's `.co/` folder (same as `.co/logs/`).

```jsonl
{"task_id":"550e8400","prompt":"Translate hello","status":"running","created":1702234567,"expires":1702320967}
{"task_id":"550e8400","prompt":"Translate hello","status":"done","result":"Hola","created":1702234567,"expires":1702320967}
```

**Why `.co/` folder?**
- Consistent with `.co/logs/` (existing pattern)
- Project-specific (each project has its own tasks)
- Already in `.gitignore`
- Easy to find (in project directory)

### API

```python
host(agent)                    # Default: 24h TTL
host(agent, task_ttl=3600)     # 1 hour
host(agent, task_ttl=604800)   # 7 days
```

### User Experience

```bash
# See all tasks
cat .co/tasks.jsonl

# Find specific task
grep "550e8400" .co/tasks.jsonl | tail -1

# Pretty print
cat .co/tasks.jsonl | jq .
```

---

## Comparison Summary

### Where to Store

| Option | Privacy | Simplicity | Offline | Chosen? |
|--------|---------|------------|---------|---------|
| Central relay | ❌ | ✅ | ✅ | ❌ |
| IPFS | ✅ | ❌ | ✅ | ❌ |
| Webhook | ✅ | ❌ | ❌ | ❌ |
| Encrypted relay | ✅ | ⚠️ | ✅ | Future |
| **Local storage** | ✅ | ✅ | ⚠️ | ✅ |

### How to Store Locally

| Format | Readable | Concurrent | Single File | Chosen? |
|--------|----------|------------|-------------|---------|
| CSV | ❌ | ❌ | ✅ | ❌ |
| JSON files | ✅ | ✅ | ❌ | ❌ |
| SQLite | ❌ | ✅ | ✅ | ❌ |
| **JSON Lines** | ✅ | ✅ | ✅ | ✅ |

---

## Principles Applied

1. **Human Readable First** - `cat tasks.jsonl` should just work
2. **Append-Only for Concurrency** - Don't fight concurrency, design it away
3. **TTL Over Complex Cleanup** - Per-task expiry is simpler than rotation
4. **Local by Default** - Privacy and simplicity over convenience
5. **Simple Over Clever** - JSON Lines is boring. Boring is good.

---

## Future Considerations

If users need more:
- **Encrypted relay storage** - Optional for cross-device access
- **IPFS integration** - For truly decentralized storage
- **SQLite mode** - For heavy query needs

But for MVP: JSON Lines with TTL. Simple, readable, works.
