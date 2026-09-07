# WebSocket Protocol

> CONNECT to start or resume, INPUT to message, EXEC to run one tool directly. Session stays alive between executions.

> This is OIP 0.1, the single ConnectOnion browser protocol. `co ai` serves it
> over the authenticated `/ws` socket and advertises it in `CONNECTED`.

---

## Rolling compatibility window

Frontend and Host deployments are not atomic. OIP 0.1 therefore follows
reader-before-writer deployment:

| Pair | Required behaviour |
|---|---|
| descriptor-less 0.1 reader ↔ current Host | accepted |
| current React ↔ descriptor-less 0.1 Host | accepted |
| current React ↔ current Host | advertised `oip/0.1` accepted |
| unsupported protocol/version | one non-retryable error; socket closes; no reconnect loop |

Within 0.1, new non-authoritative fields and events are additive. Readers ignore
what they do not understand and retain generic provider/tool rendering. Identity,
session ownership, modes, approvals, cancellation, terminal state,
and protocol/version are authoritative: malformed or unknown values are rejected
instead of guessed.

For a rename, release R reads both names; R+1 may write the new name after R is
publicly pinned; the old reader remains until at least R+2 and 30 days after R.
The descriptor-less reader remains through 1.7.x and may be removed no earlier
than 1.8.0a1, 2026-09-15, and two previews after compatibility telemetry no
longer observes it, whichever is later.

Host emits one content-free `OIP_COMPAT` record for CONNECT/reattach. It contains
only `transport=direct|relay|unknown`, `peer=legacy|oip/0.1|unsupported`, and
`outcome=accepted|rejected`; it never copies peer strings, prompts, credentials,
addresses, session IDs, or paths.

---

## Overview

Three client message types, three intents:

| Message | Intent | When |
|---------|--------|------|
| `CONNECT` | "Authenticate me, restore my session" | First message on every WebSocket |
| `INPUT` | "Run this prompt" or runtime input mid-execution | After CONNECT |
| `EXEC` | "Run this one tool directly, no LLM" | After CONNECT |

If `INPUT` arrives while the session's agent is already running, the server treats it as **runtime input** (mid-execution user input) instead of starting a second agent. The new prompt is appended to the agent's message history at the next iteration, and the server replies with `RUNTIME_INPUT_ACK` instead of starting a new OUTPUT cycle.

`EXEC` is the direct-execution fast path: it runs one named tool with no LLM, no session, and no history, replying with a single `EXEC_RESULT`. It requires the same CONNECT auth as INPUT, and the tool is gated by the host's `.co/host.yaml` permission whitelist. See [remote-call.md](remote-call.md).

On any socket — direct or through the relay — the very first frame may be
`SEAL` instead: the client offers a one-time key, the host answers `SEALED_OK`
with its own, and every frame after that — CONNECT included — travels inside
`SEALED`. See [Sealed channel](#sealed-direct-channel).

A fourth type, `ONBOARD_SUBMIT`, exists only to answer the trust gate. It is not part of the
normal path — it appears only when the server interrupts CONNECT with `ONBOARD_REQUIRED`.
See [Trust Gate](#trust-gate-onboarding).

### Scoped native-provider stop

`PROVIDER_INTERRUPT` stops one live Codex or Claude Code invocation without
cancelling its enclosing agent turn. Current clients include a bounded
`requestId`; the Host replies exactly once with:

```json
{
  "type": "PROVIDER_INTERRUPT_ACK",
  "requestId": "…",
  "invocationId": "codex:…",
  "accepted": true
}
```

`accepted: true` means the Host owns and forwarded the exact live invocation;
it is not the terminal outcome. The matching `provider_invocation` event with
`status: "cancelled"` remains authoritative. A stale or invalid target returns
`accepted: false` with the stable reason `not_active` or `invalid_request`, so
the client can restore a retry action. Legacy requests without `requestId`
retain the older no-ack behaviour during the rolling compatibility window.

### Provider-native permission change

`PROVIDER_PERMISSION_CHANGE` selects one Host-advertised Codex or Claude Code
profile for subsequent work in the exact Work Room on screen:

```json
{
  "type": "PROVIDER_PERMISSION_CHANGE",
  "requestId": "permission-1",
  "invocationId": "codex:call-7",
  "stateRevision": 4,
  "optionId": "codex:workspace-auto",
  "confirmRisk": false
}
```

The authenticated requester must own the session and be its Operator. The
option must exist in the latest durable invocation catalog and fit inside the
outer Host mode ceiling. An elevated Full Access option additionally requires
`confirmRisk: true`. Browser state is never authority.

An accepted request returns `PROVIDER_PERMISSION_ACK` with the matching request
and invocation IDs, a strictly newer revision, and the complete authoritative
`providerPermission` state. Host then streams that same revision as a canonical
`provider_invocation` for replay and other readers. A rejection has
`accepted: false` and one safe reason code such as `stale_revision`,
`ceiling_denied`, `operator_required`, or `confirmation_required`; it never
changes durable state.

When an outer `mode_change` also narrows one or more Work Rooms, the Host sends
`mode_changed` followed by one canonical `provider_invocation` per affected
Work Room. Each provider frame reflects only the transaction's final ceiling;
the Host never streams an intermediate repair under the previous mode, even if
the latest completed, failed, or cancelled continuation omitted its catalog.

```
┌────────────────────────────────────────────────────────────────┐
│                    WebSocket Lifecycle                          │
│                                                                │
│   Every connection:  WS open → CONNECT → CONNECTED → ...      │
│                                                                │
│   CONNECT carries:   auth + session + signed-command capability│
│   INPUT carries:     signed prompt/attachments (session set)   │
│                                                                │
│   Server decides:    new / connected / running                 │
│                      …or, for a caller the trust policy denies │
│                      but offers a way in: ONBOARD_REQUIRED,    │
│                      and CONNECT waits until they pass         │
│                                                                │
└────────────────────────────────────────────────────────────────┘
```

---

## Session Lifecycle

```
════════════════════════════════════════════════════════════════════
  SESSION = connection.  EXECUTION = one INPUT → OUTPUT cycle.
  Session outlives executions. Multiple INPUTs per session.
════════════════════════════════════════════════════════════════════

    ╭──────────╮
    │   new    │◄──────────────────── session_id not found
    ╰────┬─────╯
         │ CONNECT
         ↓
    ╭──────────────╮
    │  connected   │◄── agent done (OUTPUT)
    ╰──────┬───────╯
           │ INPUT
           ↓
    ╭──────────────╮
    │   running    │── agent working (LLM → tools → LLM)
    ╰──────┬───────╯
           │ agent done
           ↓
    ╭──────────────╮
    │  connected   │── 10min idle → removed
    │   (idle)     │
    ╰──────────────╯


    Two states only: 'running' (agent working) and 'connected' (idle, alive).
    WS disconnect does NOT change session.status — IO queues survive the WS,
    a reconnecting client just re-subscribes via CONNECT { last_msg_id }.

    Cleanup: 'connected' after 10min idle, 'running' after 1h (stuck-agent cap).
```

---

## Protocol Flows

### New Session

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ─────────────────────────────►│  verify Ed25519 signature
  │   { auth, session: {messages} }         │  no session_id → new session
  │                                         │  store conversation history
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc", status: "new" }
  │                                         │
  │◄── PING ───────────────────────────────│  keep-alive starts (every 30s)
  │── PONG ────────────────────────────────►│
  │                                         │
  │── INPUT ───────────────────────────────►│  run agent with prompt
  │   { prompt: "hello" }                   │  (no session in INPUT)
  │                                         │
  │◄── thinking ───────────────────────────│  stream events
  │◄── tool_call ──────────────────────────│
  │◄── OUTPUT ─────────────────────────────│  { result, session }
  │                                         │  session → "connected" (not dead)
  │                                         │
  │── INPUT ───────────────────────────────►│  same WS, same session
  │   { prompt: "tell me more" }            │
  │◄── ... ────────────────────────────────│
  │◄── OUTPUT ─────────────────────────────│
```

### Resume After Page Refresh (agent still running)

```
Client                                    Server
  │                                         │
  │    (agent still running on server)      │
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ─────────────────────────────►│  verify signature
  │   { session_id: "abc", session: {...} } │  registry.get("abc") → running
  │                                         │  merge sessions if server newer
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc", status: "running" }
  │◄── buffered events ───────────────────│  drain queued events
  │◄── PING ───────────────────────────────│  keep-alive resumes
  │                                         │
  │◄── stream events ─────────────────────│  live again
  │◄── OUTPUT ─────────────────────────────│
```

### Resume After Page Refresh (agent finished)

```
Client                                    Server
  │                                         │
  │    (agent finished while client away)   │
  │                                         │
  │── WS open ────────────────────────────►│
  │                                         │
  │── CONNECT ─────────────────────────────►│  verify signature
  │   { session_id: "abc", session: {...} } │  registry.get("abc") → connected
  │                                         │  merge: server has newer data
  │                                         │
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc",
  │                                         │    status: "connected",
  │                                         │    server_newer: true,
  │                                         │    session: {merged},
  │                                         │    chat_items: [...] }
  │                                         │
  │    (client updates UI with server data) │
  │                                         │
  │── INPUT ───────────────────────────────►│  ready for next prompt
  │   { prompt: "what else?" }              │
  │◄── ... ────────────────────────────────│
  │◄── OUTPUT ─────────────────────────────│
```

### Session Not Found (expired or never existed)

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │── CONNECT { session_id: "abc" } ──────►│  not in registry
  │◄── CONNECTED ──────────────────────────│  { session_id: "abc", status: "new" }
  │                                         │
  │── INPUT ───────────────────────────────►│  fresh session, full history from CONNECT
```

### Trust Gate (onboarding)

An agent whose trust policy denies strangers can still let them earn their way in — an
invite code, or a payment. That negotiation happens **inside CONNECT**, before any message
is sent.

```
Client                                    Server
  │                                         │
  │── WS open ────────────────────────────►│
  │── CONNECT ─────────────────────────────►│  verify Ed25519 signature — OK
  │   { payload, from, signature }          │  trust policy: this caller is denied
  │                                         │  …but onboard methods are configured
  │                                         │  stash the CONNECT, do not answer it yet
  │◄── ONBOARD_REQUIRED ───────────────────│  { methods: ["invite_code"] }
  │                                         │
  │   (client shows a code prompt)          │
  │                                         │
  │── ONBOARD_SUBMIT ──────────────────────►│  signed again, invite_code in payload
  │   { payload: { invite_code }, … }       │  verify_invite()
  │                                         │
  │◄── ONBOARD_SUCCESS ────────────────────│  { level: "contact" }  ← caller promoted
  │◄── CONNECTED ──────────────────────────│  the stashed CONNECT, now resumed
  │                                         │
  │── INPUT ───────────────────────────────►│  the conversation the caller came for
```

Three things follow from this shape, and each one is a mistake a client can make:

**The answer arrives before the first message.** A client that opens the socket on a
landing page — to receive `DASHBOARD_SNAPSHOT`, say — already has the gate's answer in hand
before the reader types anything. There is no need to send a message and watch it be
refused, and no need to guess from `/info`: that endpoint is anonymous and tells an admin
exactly what it tells a stranger, so a client that gates on it puts a code prompt in front
of people who hold the keys.

**A refused code is an `ERROR`, not another `ONBOARD_REQUIRED`.** The gate does not re-ask.
The reply is `{"type": "ERROR", "message": "Invalid invite code"}`, and a client that waits
for a second `ONBOARD_REQUIRED` to detect the refusal will wait forever, leaving the reader
staring at a form that never responds.

**The stashed CONNECT is resumed by the server, not replayed by the client.** Do not send
CONNECT again after `ONBOARD_SUCCESS`. Its signature carries a timestamp with a five-minute
window, and a human reading a card, finding a code and typing it can easily outlast that —
the resend would be rejected as expired. The server holds the original and completes it
itself, with the address the onboard verified.

A real capture of a first-time visitor on a gated agent, all on one socket:

```
ONBOARD_REQUIRED → ONBOARD_SUCCESS → CONNECTED → AGENT_PROFILE
→ DASHBOARD_SNAPSHOT → (INPUT) → … → OUTPUT → SESSION_STATUS
```

See [../features/trust.md](../features/trust.md) for configuring `onboard` in `trust.md`.

---

## Message Reference

### Client → Server

#### CONNECT

Authenticate, restore session, and sync conversation. **Always the first message.**

```json
{
  "type": "CONNECT",
  "session_id": "550e8400-...",
  "session": { "messages": [...], "mode": "default" },
  "last_msg_id": "ev-9f12...",
  "payload": {
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567,
    "signed_commands": 1
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `session_id` | No | Session to resume. Omit for new session. |
| `session` | No | Conversation history (messages, mode, etc.) |
| `last_msg_id` | No | ID of the last agent event the client fully rendered. On resume of a `running` session, server rewinds its event cursor to right after this id and replays anything the client missed. Omit (or pass `null`) to replay all in-flight events of the current execution. |
| `payload` | Yes | Signed payload for authentication |
| `from` | Yes | Client's public address |
| `signature` | Yes | Ed25519 signature of payload |

`payload.signed_commands: 1` is itself signed. It opts the connection into the
v2 command gate described below. A new server continues accepting a v1 CONNECT
without it, so an older client is not stranded; it does not receive v2's
per-command injection/replay protection.

Server response based on state:

| session_id | Server state | Response status | Server action |
|------------|-------------|-----------------|---------------|
| Not provided | — | `"new"` | Allocate new session |
| Provided | In registry, running | `"running"` | Reattach IO, pipe buffered events |
| Provided | In registry, connected | `"connected"` | Merge sessions, reset idle timer |
| Provided | Not found | `"new"` | Allocate new session (same id) |
| Provided | Owned by another caller | `"new"` | Allocate new session, **new id** |

A session belongs to whoever started it. Naming someone else's id gets a fresh
session with a *different* id, reported in CONNECTED — not theirs, and not an
error, which would confirm the session exists. Keeping the requested id would
mean your turn overwrote their history.

**CONNECTED is not the only possible reply.** If the trust policy turns this caller away
and the agent offers a way in, the server answers `ONBOARD_REQUIRED` instead and holds the
CONNECT open until the caller passes — see [Trust Gate](#trust-gate-onboarding) below. If
the policy turns them away and offers nothing, the reply is `ERROR`.

"Offers a way in" means a door that actually opens, not one that is merely
written down. The shipped policy declares `invite_code: [$CO_INVITE_CODE]` and
`payment: $CO_PAYMENT`; with neither set, nothing resolves and there is no
onboarding to offer, so a stranger gets `ERROR` from the policy rather than an
`ONBOARD_REQUIRED` leading nowhere.

**A signature is single-use.** Replaying a captured CONNECT is refused with
`ERROR unauthorized: this CONNECT was already used`. A v2 client also signs every
application command; replaying one is refused with `signed command already used`.
The one-use ledger is shared across ASGI workers and survives a worker restart;
it stores only short-lived signature digests in `.co/replay.sqlite3`.
Each digest remains until its signed timestamp is cryptographically expired;
an unavailable or locked ledger fails closed.
CONNECT processing verifies Ed25519 first, atomically claims the digest second,
and only then evaluates trust or onboarding policy. A replay therefore cannot
repeat an LLM policy call or a policy side effect.

**A v2 command signs what the server executes.** Its payload contains `type`, all
command fields, `to`, `timestamp`, and a random `nonce`. The server verifies the
signer is the caller that opened this connection, verifies the recipient and
type, then discards the unsigned compatibility copy and dispatches the signed
payload. INPUT, EXEC, runtime input, approval responses and ask-user responses
all pass through this gate. PONG is a transport frame. SESSION_STATUS uses the
verified CONNECT identity on a live socket, or an independently signed v2 frame
on a temporary socket, and only reveals a session owned by that identity.
ONBOARD_SUBMIT and ADMIN frames retain their existing independent signatures.

This decision is made **per caller**, after the signature is verified, so an admin, a
contact, or anyone who onboarded earlier never sees the gate at all.

#### INPUT

Send a prompt. Only valid after CONNECTED. **No session data — just the prompt.**

```json
{
  "type": "INPUT",
  "prompt": "Translate hello to Spanish",
  "images": ["data:image/png;base64,..."],
  "files": [{ "name": "doc.pdf", "data": "data:application/pdf;base64,..." }],
  "payload": {
    "type": "INPUT",
    "input_id": "7c2a...",
    "prompt": "Translate hello to Spanish",
    "images": ["data:image/png;base64,..."],
    "files": [{ "name": "doc.pdf", "data": "data:application/pdf;base64,..." }],
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567,
    "nonce": "550e8400-..."
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

The command fields remain at the top level only so a v2 client can talk to a v1
host. A v2 host executes the verified `payload`, never those duplicates.

If sent while the session's agent is already running, this message is routed as runtime input: the prompt is appended to the running agent's message history (with framing telling the LLM to treat it as additional context, not a replacement) and the server replies `RUNTIME_INPUT_ACK` instead of starting a new OUTPUT cycle. No new `thinking` chat item is created — the existing one keeps streaming.

#### EXEC

Run one registered tool directly — no LLM, no session, no history. Only valid after CONNECTED. The server replies with a single `EXEC_RESULT`.

```json
{
  "type": "EXEC",
  "exec_id": "7c2a...",
  "tool": "bash",
  "args": { "command": "co status" },
  "payload": {
    "type": "EXEC",
    "exec_id": "7c2a...",
    "tool": "bash",
    "args": { "command": "co status" },
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567,
    "nonce": "550e8400-..."
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

The tool is checked against the host's `.co/host.yaml` permission whitelist (the same list the LLM approval flow uses); a tool that isn't whitelisted comes back as an `EXEC_RESULT` with `status: "error"`. Each `EXEC` runs as its own server-side task, so a slow tool never blocks the connection, and `exec_id` correlates the reply — several `EXEC`s can be pipelined on one socket.

#### PONG

```json
{ "type": "PONG" }
```

#### ASK_USER_RESPONSE

```json
{ "type": "ASK_USER_RESPONSE", "answer": "Python 3" }
```

#### APPROVAL_RESPONSE

```json
{ "type": "APPROVAL_RESPONSE", "approved": true, "scope": "once" }
```

Approval responses are consumed once and are bound to the currently pending
request.

#### mode_change

An authenticated client selects one Host-advertised permission mode:

```json
{
  "type": "mode_change",
  "mode": "auto"
}
```

The request is accepted only while the durable session is idle and owned by
the authenticated caller. `read-only` and `auto` are always available;
`full-access` is offered only under a positive Host launch ceiling. Every
authenticated participant receives the same available modes. No client field
can supply or extend Full access turns. Success is `mode_changed` and
means the durable commit completed; busy, policy, ownership, and persistence
failures return `ERROR`.
`@connectonion/react` owns this browser operation; O Chat consumes it without
constructing protocol frames. Plan is not a mode; Todo List progress carries
no authority.

#### ONBOARD_SUBMIT

Pass the trust gate. Sent in reply to `ONBOARD_REQUIRED`, on the same socket.

```json
{
  "type": "ONBOARD_SUBMIT",
  "payload": {
    "invite_code": "B7HSW-6Y6P4-BZC5Z",
    "to": "0x3d4017c3e843...",
    "timestamp": 1702234567
  },
  "from": "0xClientPublicKey",
  "signature": "0x..."
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `payload.invite_code` | One of the two | A code the agent's `trust.md` lists under `onboard.invite_code` |
| `payload.payment` | One of the two | Amount claimed paid, for `onboard.payment`. This is an assertion the host verifies — nothing is charged over this socket |
| `payload.timestamp` | Yes | Same five-minute window as CONNECT. Signed fresh here, which is the point: the original CONNECT's may have aged out while the reader typed |
| `from` / `signature` | Yes | Signed exactly like CONNECT |

Sent on the same socket as the CONNECT it answers. A wrong code comes back as `ERROR` and
the stashed CONNECT is **kept**, so the reader can simply try again — no reconnect needed.

#### SEAL / SEALED_OK / SEALED {#sealed-direct-channel}

End-to-end encryption for a socket, direct or relayed. A host may announce
plain `ws://IP:port` and needs no domain, certificate or TLS front, and a
session through the relay is opaque to the relay. Before this a signed CONNECT
captured on a plaintext link could be replayed inside its five-minute window
(#649), direct connections were therefore limited to TLS or loopback, and the
relay — which terminates TLS — read every frame it forwarded.

Handshake, first two frames on the socket:

```json
{"type": "SEAL", "to": "0xHOST", "from": "0xCLIENT",
 "ephemeral": "<hex X25519 public key, one-time>", "timestamp": 1756800000,
 "signature": "<Ed25519 over the canonical JSON of the other five fields, by 0xCLIENT>"}

{"type": "SEALED_OK", "to": "0xCLIENT", "from": "0xHOST",
 "ephemeral": "<hex X25519 public key, one-time>", "client_ephemeral": "<the SEAL's key>",
 "signature": "<Ed25519 over the canonical JSON of the other five fields, by 0xHOST>"}
```

Both sides derive one NaCl `Box` from the two one-time keys. The address *is*
the Ed25519 public key, so each side verifies the other's signature with
nothing but the address it already had; no directory, and the relay is not
involved. A `SEAL` older than the CONNECT freshness window, addressed to
another host, or signed by someone other than `from` is answered with
`ERROR seal refused: …` and the socket is closed (code 4003) — no plaintext
second try.

Through the relay the frames are the same. The relay proxy reads `to` from the
first frame to pick the agent and forwards every frame after it verbatim,
adding only `session_id`; `SEAL` carries `to`, so nothing on the relay changes.
The relay's own frames to the client — its 30s `PING` and an `ERROR` such as
`Agent not connected` — arrive in the clear and are passed up as-is; they hold
no key and carry nothing a peer said. Everything else on a sealed socket must
open.

Every later frame in either direction:

```json
{"type": "SEALED", "n": 7, "c": "<base64 ciphertext>"}
```

`n` is a per-direction counter starting at 1; the nonce is the direction tag
plus `n`, so a captured frame replayed or reordered fails to open and ends the
session. Inside `c` is the ordinary frame (CONNECT, INPUT, EXEC, PING/PONG,
PROXY_STREAM…), and the router never sees the difference. Signed CONNECT and
v2 command signatures are still required inside the seal: the seal makes the
link private, the signatures still say who is speaking.

Inside a seal the `CONNECT` (and an `ONBOARD_SUBMIT`) must be signed by the
identity that signed the `SEAL`; a frame from anyone else is refused as
`unauthorized: … not signed by the sealed peer`. That binding is what makes
the host's one-use signature ledger unnecessary on a sealed socket: nobody
but the sealed peer can put a frame on it, so a captured signature cannot be
presented there by anyone else, and the ledger is not consulted. A bare
socket — an older client — is still held to the ledger. A `co host` process
runs one worker and keeps that ledger in memory; only `create_app()` served
with several uvicorn workers keeps it in `.co/replay.sqlite3`, and that file
now heals if it is removed under a running host (#1403).

Client rule (`_open_best_connection`): every socket, direct or relayed, is
offered a `SEAL` when the client has keys. A direct host that does not answer
`SEALED_OK` is used bare only if the link is already private — TLS or
loopback; otherwise the socket is closed and the client moves on to the relay.
A relay host that does not answer (a 1.8.0 host) has already consumed that
socket's first frame, so the client closes it and opens a fresh bare relay
socket — TLS to the relay, every client's footing before 1.8.1. `PROXY_ATTACH`
still requires a direct socket; a sealed plaintext one qualifies.

#### PROXY_ATTACH

Lend this computer's internet connection to the host (`co proxy share`). Sent
once per socket after a signed CONNECT, on a **direct** connection only — the
relay never carries page bytes. Signed like every other command.

```json
{
  "type": "PROXY_ATTACH",
  "payload": {
    "grant": {
      "type": "proxy_grant", "grant_id": "pxg_...",
      "grantor": "0xLaptop", "holder": "0xHost", "scope": "public_internet",
      "expires_at": "2026-09-03T10:00:00Z", "max_bytes": null,
      "signature": "..."
    },
    "to": "0xHost", "timestamp": 1702234567, "nonce": "..."
  },
  "from": "0xLaptop",
  "signature": "0x..."
}
```

The host verifies the grant (it must name this host as holder, be unexpired,
and be signed by the identity on this socket), requires contact-or-better
trust, and answers `PROXY_ATTACHED` or `ERROR`. A later attach from the same
identity replaces the earlier one; the attachment ends when the socket closes.

#### PROXY_STREAM

One multiplexed stream operation, in either direction, while a share is
attached. The host opens streams; the laptop answers them.

```json
{"type": "PROXY_STREAM", "payload": {"id": 7, "op": "connect", "address": "93.184.216.34", "port": 443}}
```

| `op` | Direction | Fields | Meaning |
|------|-----------|--------|---------|
| `resolve` | host → laptop | `host`, `port` | resolve this name with the laptop's DNS and policy |
| `resolve` | laptop → host | `addresses` | the complete answer set |
| `connect` | host → laptop | `address`, `port` | open a socket to this numeric address, re-classified on the laptop |
| `connect` | laptop → host | — | the socket is open |
| `data` | both | `data` (base64, ≤ 32 KiB) | bytes on the stream |
| `eof` | both | — | half-close: no more bytes this way |
| `close` | both | — | the stream is finished; forget it |
| `error` | both | `code` | the request failed (`EGRESS_*` / `DESTINATION_*` codes) |

Laptop → host frames are signed like every command. Host → laptop frames carry
no signature: they travel inside the TLS session the laptop opened to an
endpoint whose identity it already verified. At most 64 streams per share; the
grant's `expires_at` and `max_bytes` are enforced by the host.

### Server → Client

#### CONNECTED

Response to CONNECT.

```json
{
  "type": "CONNECTED",
  "session_id": "550e8400-...",
  "status": "new",
  "protocol": {"name": "oip", "version": "0.1"},
  "session_modes": {
    "currentModeId": "auto",
    "turnsLeft": null,
    "availableModes": [
      {"id": "read-only", "name": "Read only"},
      {"id": "auto", "name": "Auto"},
      {"id": "full-access", "name": "Full access"}
    ]
  },
  "server_newer": true,
  "session": { "messages": [...] },
  "chat_items": [...]
}
```

| `status` | Meaning | Client action |
|----------|---------|---------------|
| `"new"` | Fresh session | Send INPUT when ready |
| `"connected"` | Session alive, idle | Send INPUT when ready |
| `"running"` | Agent still running | Wait for events/OUTPUT |

`server_newer`, `session`, and `chat_items` are only included when the server's session data is newer than the client's (e.g., agent completed while client was away).
`session_modes` is the authoritative current/available state for this
authenticated identity when Host mode policy is enabled.

#### OUTPUT

Execution completed. **Session stays alive for next INPUT.**

```json
{
  "type": "OUTPUT",
  "result": "Hola",
  "session_id": "550e8400-...",
  "duration_ms": 1250,
  "session": { "messages": [...], "trace": [...], "turn": 2 }
}
```

The session may contain a canonical `plan` array. It is current replacement
state, not a transcript entry, and is preserved across session sync, reconnect,
and final output.

#### plan

After a successful TodoList state change, the Host sends one complete plan:

```json
{
  "type": "plan",
  "entries": [
    {"content": "Run tests", "priority": "high", "status": "in_progress"},
    {"content": "Update docs", "priority": "medium", "status": "pending"}
  ]
}
```

Every update replaces the complete plan; an empty `entries` list clears it.
The plan has no message or plan ID. The event is observational and cannot
grant execution permission or change the session mode.

#### EXEC_RESULT

Reply to an `EXEC`. `exec_id` echoes the request. `result` is the tool's raw output — text, or a base64 data URL for a screenshot tool.

```json
{
  "type": "EXEC_RESULT",
  "exec_id": "7c2a...",
  "tool": "bash",
  "status": "success",
  "result": "...raw output...",
  "duration_ms": 42
}
```

On failure (tool raised, not whitelisted, unknown tool): `status: "error"` with an `error` field instead of `result`.

#### PING

Keep-alive. Sent every 30 seconds.

```json
{ "type": "PING" }
```

#### Stream Events

| Type | Description |
|------|-------------|
| `thinking` | Agent reasoning |
| `tool_call` | Tool execution started |
| `tool_result` | Tool execution completed |
| `ask_user` | Agent needs human input |
| `approval_needed` | Tool requires approval |
| `plan` | Complete observational TodoList replacement |
| `compact` | Context compaction |

#### AGENT_PROFILE

What the agent is — name, model, tools, **every** skill, and the account balance for
managed-key agents. Sent once, right after `CONNECTED`.

```json
{
  "type": "AGENT_PROFILE",
  "session_id": "550e8400-...",
  "name": "my-agent",
  "address": "0x3d4017c3...",
  "model": "co/gemini-3.8-flash",
  "tools": ["search", "shell"],
  "skills": [
    {"name": "co-browser", "description": "drive a browser", "location": "project"},
    {"name": "my-notes", "description": "personal", "location": "user"}
  ],
  "balance_usd": 25.34
}
```

**This is the authenticated answer, and it is deliberately larger than the public one.**
`GET /info` and the relay directory are reachable by anyone and publish only skills from
the project tree (`project`, `claude-project`); the operator's personal skills in
`~/.co/skills` and `~/.claude/skills` stay private there. This frame arrives past the
signature check and the trust gate, so it carries all of them.

A client that has not connected — or has not passed onboarding — should show the public
answer and not treat it as an incomplete version of this one. It is what that viewer is
entitled to see.

React package: `agent.profile` and `useAgentForHuman().profile`, `null` until the
frame lands.

**There is a third profile surface, and it is not this one.** `host()` also sends a
profile to the relay inside its `ANNOUNCE` frame — that is what registers the agent and
puts it in the public directory, and it is built separately by
`_build_agent_profile()` in `network/host/server.py`. Same public skill subset as
`/info`, different code path, different size limits, enforced by the relay rather than
by the agent. If an agent starts cleanly but reads as offline, that is the surface to
look at: the relay rejects the whole ANNOUNCE when the profile fails validation, and
`host()` prints the reason as `Relay error: <reason>` and keeps heartbeating. The
contract is documented in `oo-api/docs/relay-announce-profile.md`.

#### DASHBOARD_SNAPSHOT

The agent's Control Center HTML (customized through the compatible
`dashboard.html` filename) for the client to render beside chat. Sent right after
`CONNECTED` so the Control Center paints before any input, and again after
`OUTPUT` when the run changed the file. Agents without a `dashboard.html` never send
it, and the frame is skipped when the file hasn't changed since this connection last
saw it.

```json
{
  "type": "DASHBOARD_SNAPSHOT",
  "html": "<!DOCTYPE html>…",
  "session_id": "550e8400-..."
}
```

The HTML is agent-authored and untrusted: clients render it in a sandboxed iframe with
scripting and network access blocked. Files over 2MB are not sent. See
[dashboard.md](dashboard.md).

#### RUNTIME_INPUT_ACK

Acknowledges an INPUT that arrived while the agent was running. The prompt has been queued and will be picked up at the agent's next iteration.

```json
{
  "type": "RUNTIME_INPUT_ACK",
  "session_id": "550e8400-...",
  "id": "runtime-input-7c2a..."
}
```

#### ONBOARD_REQUIRED

The trust gate, in reply to CONNECT. The caller's signature checked out, but the policy
denies them — and the agent offers a way in. The CONNECT is **held open**, not failed.

```json
{
  "type": "ONBOARD_REQUIRED",
  "identity": "0xCallerPublicKey",
  "methods": ["invite_code", "payment"],
  "payment_amount": 10,
  "payment_address": "0xAgentAddress"
}
```

| Field | Present | Description |
|-------|---------|-------------|
| `identity` | Always | The address that was just authenticated — the caller, echoed back |
| `methods` | Always | Which of `invite_code` / `payment` this agent accepts. Show only these |
| `payment_amount` | With `payment` | Amount, from `onboard.payment` in `trust.md` |
| `payment_address` | With `payment` | Where to send it |

Answer with `ONBOARD_SUBMIT`. Note what is *not* here: no session, no status. Nothing has
been established yet.

#### ONBOARD_SUCCESS

The submitted proof was accepted and the caller has been promoted. `CONNECTED` follows on
its own — the server completes the CONNECT it stashed, so **do not send CONNECT again**.

```json
{
  "type": "ONBOARD_SUCCESS",
  "identity": "0xCallerPublicKey",
  "level": "contact",
  "message": "Invite code verified. You are now a contact."
}
```

`level` is the trust level actually granted, read back from the policy after promotion —
not a value the client chose. From here the connection proceeds exactly as an ungated one.

#### ADMIN_RESULT

Reply to `ADMIN_PROMOTE` / `ADMIN_DEMOTE` from an admin caller.

```json
{ "type": "ADMIN_RESULT", "action": "promote", "ok": true, "level": "whitelisted" }
```

Fields beyond `action` are whatever the trust handler returned for that operation.

#### ERROR

```json
{ "type": "ERROR", "message": "Something went wrong" }
```

Also how a **refused onboard** comes back — `{"type": "ERROR", "message": "Invalid invite
code"}`. There is no dedicated failure frame, and no repeat of `ONBOARD_REQUIRED`: a client
waiting for one of those to detect the refusal will wait forever.

#### PROXY_ATTACHED

The share offered by `PROXY_ATTACH` is accepted and registered under the
sender's address. A refused attach is an `ERROR` whose message starts with
`proxy attach refused:`.

```json
{ "type": "PROXY_ATTACHED", "expires_at": "2026-09-03T10:00:00Z", "max_bytes": null }
```

From here the host sends `PROXY_STREAM` frames (unsigned, see above) down this
socket until it closes.

---

## Architecture Diagram

```
════════════════════════════════════════════════════════════════════

  ╔══════════════╗                    ╔═══════════════════════════╗
  ║   oo-chat    ║                    ║     Agent Server          ║
  ║  (browser)   ║                    ║  (Python SDK + host())    ║
  ╠══════════════╣                    ╠═══════════════════════════╣
  ║              ║                    ║                           ║
  ║ localStorage ║    WebSocket       ║  ┌─────────────────────┐  ║
  ║ ┌──────────┐ ║   ┌──────────┐    ║  │ ActiveSessionRegistry│  ║
  ║ │ session  │ ║───│ /ws      │────║──│                     │  ║
  ║ │ chatItems│ ║   └──────────┘    ║  │ session_id → {      │  ║
  ║ │ messages │ ║    CONNECT ──►    ║  │   io, thread,       │  ║
  ║ └──────────┘ ║    ◄── CONNECTED  ║  │   status, last_ping │  ║
  ║              ║    INPUT ────►    ║  │ }                   │  ║
  ║ TS SDK       ║    ◄── events     ║  └─────────┬───────────┘  ║
  ║ RemoteAgent  ║    ◄── OUTPUT     ║            │              ║
  ║              ║    PING/PONG      ║            ↓              ║
  ╚══════════════╝                    ║  ┌─────────────────────┐  ║
                                      ║  │ SessionStorage      │  ║
                                      ║  │ (.co/session_       │  ║
                                      ║  │  results.jsonl)     │  ║
                                      ║  └─────────────────────┘  ║
                                      ╚═══════════════════════════╝

  Data Ownership:
  ┌────────────────────────────────────────────────────────────────┐
  │ Client owns: conversation history (localStorage)              │
  │ Server owns: execution state (registry), results (storage)    │
  │ CONNECT syncs: client → server (session), server → client     │
  │                (if server_newer)                               │
  └────────────────────────────────────────────────────────────────┘

════════════════════════════════════════════════════════════════════
```

---

## Separation of Concerns

```
┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐
│   Connection    │  │  Conversation   │  │   Execution     │
│                 │  │                 │  │                 │
│ WebSocket + auth│  │ Message history │  │ One INPUT→OUTPUT│
│ PING/PONG       │  │ Owned by client │  │ Agent thread    │
│ Persistent      │  │ Sent via CONNECT│  │ Temporary       │
│                 │  │ Merged on server│  │                 │
│ Dies: WS close  │  │ Dies: never     │  │ Dies: OUTPUT    │
│ + 10min grace   │  │ (localStorage)  │  │                 │
└─────────────────┘  └─────────────────┘  └─────────────────┘
```

---

## Authentication

Authentication happens once, on CONNECT.

```
CONNECT (signed)          INPUT (not signed)
  │                          │
  ▼                          ▼
Server verifies            Server trusts
signature → OK             (same WS, already authenticated)
```

Trust levels:

| Trust Level | CONNECT Behavior |
|-------------|-----------------|
| `open` | Accept without signature |
| `careful` | Accept unsigned, recommend signature |
| `strict` | Require valid signature |

---

## Client Reconnect

```
Page loads → Zustand hydrates → session_id exists?
  │
  ├── Yes → CONNECT { session_id, session: {messages} }
  │           │
  │           ├── "new"       → session expired, start fresh (client has history)
  │           ├── "connected" → session alive, ready for INPUT
  │           └── "running"   → agent running, events will stream
  │
  └── No  → show empty state, wait for user input
              → CONNECT (no session_id) on first message
```

---

## Before vs After

### Before (v0.9.x) — INIT + ATTACH

```
WS open → INIT { auth }    → CONNECTED { status: "new" }
           INPUT { prompt, session }  → events → OUTPUT → session dies
```

### v0.10.x — CONNECT (unified)

```
WS open → CONNECT { auth, session_id? } → CONNECTED { status }
           INPUT { prompt, session }     → events → OUTPUT → session dies
```

### v0.11.x — Session survives execution (current)

```
WS open → CONNECT { auth, session_id?, session }
           → CONNECTED { status: new/connected/running }

           INPUT { prompt }   → events → OUTPUT  (session stays alive)
           INPUT { prompt }   → events → OUTPUT  (again, same session)
           INPUT { prompt }   → events → OUTPUT  (and again)

WS close → 10min grace → session cleaned up
```

---

## Server Console Output

The WebSocket handler prints structured status lines to the server console. Designed for quick scanning: routine messages are compact, data flow events are indented sub-lines.

### Connection lifecycle

```
⚡ ws+ 127.0.0.1 (0 active)        # new WebSocket, show active session count
✓ CONNECT identity=0x2f3d... session=aad5... status=new
✓ INPUT identity=0x2f3d... session=aad5... prompt=hello world...
⚡ ws- (1 active)                    # disconnect, show remaining sessions
```

### Data flow visibility

When client data is accepted, merged, or reattached, indented sub-lines show what's happening:

```
✓ CONNECT identity=0x2f3d... session=aad5... status=connected
  ↑ client session: 4 messages       # client sent conversation history
  ↕ merged sessions (server newer)   # server had newer data, merged
```

```
✓ CONNECT identity=0x2f3d... session=aad5... status=running
  ↻ reattaching to running agent     # reconnecting to in-progress execution
```

```
✓ INPUT identity=0x2f3d... session=aad5... prompt=analyze this...
  ↑ 2 images, 1 files                # client sent attachments
```

### What's suppressed

Routine message types that already have their own status lines don't print a generic `← WS recv:` line:
- `CONNECT`, `INPUT`, `SESSION_STATUS`, `PONG`

Non-routine types still print:
```
← WS recv: ONBOARD_SUBMIT
← WS recv: ADMIN_PROMOTE
```

### Error lines

```
✗ CONNECT auth error: forbidden
✗ INPUT rejected: not authenticated (send CONNECT first)
✗ agent error: <exception message>
```

---

## Key Files

| File | Role |
|------|------|
| `network/host/ws_router/` | 4-file message router package — `session.py` (run_ws_session main loop), `connect.py` (handle_connect), `agent_io.py` (start_agent / resume_forwarding / forwarding), `ping.py` (keepalive) |
| `network/asgi/websocket.py` | ASGI adapter — wraps ASGI primitives into send_msg/recv_msg for ws_router |
| `network/relay.py` | Relay adapter — wraps asyncio.Queue/relay WS into send_msg/recv_msg for ws_router |
| `network/host/session/active.py` | ActiveSessionRegistry — in-memory session tracking |
| `network/io/websocket.py` | WebSocketIO — queue bridge between async/sync |
| `network/host/session/storage.py` | SessionStorage — JSONL persistence |
| `network/host/session/merge.py` | Session merge conflict resolution |
