# DD-063: A listener is a second ingress, not a second authority

**Status:** Proposed

**Date:** 2026-09-02

**Related:** [Issue #1389](https://github.com/openonion/connectonion/issues/1389),
[Issue #1310](https://github.com/openonion/connectonion/issues/1310),
[Issue #349](https://github.com/openonion/connectonion/issues/349),
[Issue #1360](https://github.com/openonion/connectonion/issues/1360),
[044 One permission-mode contract](044-canonical-approval-mode-vocabulary.md),
[053 One browser protocol, native coding adapters](053-oip-only-browser-and-native-coding-adapters.md)

## Context

A deployed Agent has exactly one way to be woken today: an OIP peer that holds
an Ed25519 key sends `INPUT` over `/ws`, or a clock entry in `.co/schedule.yaml`
fires. Nobody who lives in Feishu, WhatsApp, Telegram or Slack can reach it.
Seven inbound-channel issues exist and none has code (#1389 has the audit).

`co listen feishu` (#1310) is the first fully specified one. Before building
it, this decision fixes what every listener after it must share, because the
things that go wrong here are not provider-specific. They were all observed in
the field during 2026 in the product closest to what we are building:

- **The control plane is the attack surface, not the adapter.** OpenClaw's
  gateway went from ~1,000 to 21,639 publicly exposed instances in one week
  (Censys, 2026-01-31) and to 135,000+ by 2026-02-09 (SecurityScorecard). Its
  CVEs were in the gateway and Control UI (token leaked through a `gatewayUrl`
  query parameter, an unauthenticated bootstrap endpoint, mDNS-supplied TLS
  pins), not in the channel code.
- **In-memory dedup does not survive an outage.** OpenClaw dedupes inbound
  messages in a 20-minute in-process cache. During an LLM outage Telegram
  redelivered one message about 50 times and every copy ran when the API
  recovered (openclaw#58611). A restart also replayed duplicates (openclaw#8140).
- **Metadata is prompt.** Contact names, vCard fields, location labels and
  group titles were flattened into the model's context until Imperva showed
  they carried injected instructions; OpenClaw 2026.4.23 moved them into
  fenced untrusted JSON. Link previews turned a reply into a zero-click
  exfiltration channel (PromptArmor).
- **Room membership is not authority.** Both OpenClaw and Claude Code's
  channels converged on the same rule after public bots became injection
  endpoints: gate on the sender's identity, default to pairing, require an
  @mention in groups. Claude Code's reference text: *"gating on the room would
  let anyone in an allowlisted group inject messages into the session."*
- **Shared sessions are a footgun.** OpenClaw's default let every DM share
  one conversation; its own docs now warn to enable isolation if more than one
  person can message the agent.
- **Unofficial transports get banned.** OpenClaw's WhatsApp runs on Baileys;
  supervised restarts produced reconnect loops and 48-72 hour account
  restrictions (openclaw#16270). A request for the official Cloud API was
  closed as not planned (openclaw#23093).

The platforms themselves agree on the delivery contract. Feishu, Slack and
Slack Socket Mode give the receiver three seconds to acknowledge; Feishu then
retries at 15 s, 5 min, 1 h and 6 h; Meta retries WhatsApp webhooks with
decreasing frequency for up to seven days; none guarantees order. Every one
of them delivers at least once and says so. Feishu documents the dedup key for
`im.message.receive_v1` as `message_id`, and its reply endpoint takes a caller
`uuid` that succeeds at most once per hour. Stripe's published webhook rules
are the same list: verify, return 2xx fast, dedupe on the event id, process
asynchronously, expect out-of-order.

ConnectOnion already owns most of the primitives this needs, and they are
worth naming because a listener that bypasses them is what this decision
forbids:

- `connectonion/network/host/schedule.py` is a long-lived loop inside the
  Host. Its header argues that the clock lives in-process because `co` runs on
  three operating systems and their schedulers rot; its `_run_entry` reuses
  `input_handler` so a scheduled run lands in `.co/session_results.jsonl`
  beside interactive ones, "same record, same fields".
- `connectonion/network/host/replay.py` is a cross-worker one-use ledger in
  SQLite: `BEGIN IMMEDIATE`, a bounded busy timeout, and a typed error so
  callers fail closed.
- `connectonion/network/host/session/mode.py:claim_host_prompt` is the atomic
  single-writer claim per session; a busy session answers `_busy()`.
- The trust system (`open`, `careful`, `strict`, whitelist, admins, onboarding
  by invite code) is the only authority. DD-044 is the only permission-mode
  contract. `.co/host.yaml` is where an operator says how open a host is.
- `useful_tools/sms.py` already returns every message with `"trusted": False`
  and never executes it as an instruction.

## Decision

### 1. A listener lives inside the Host, as a lifespan, not as a second process

A listener is composed into `host()` the way the relay and the schedule are:
an `(on_startup, on_shutdown)` pair. The deployed unit stays one process with
one supervisor. There is no second daemon and no IPC boundary between "the
thing that hears Feishu" and "the thing that runs the Agent".

`co listen feishu` remains a real foreground command, as #1310 specifies. It
starts a Host bound to loopback with that one listener enabled, prints what it
is connected to, and stops on Ctrl-C. `--check` validates configuration and
subscription and exits. `--once` handles one accepted event and exits. On a
deployed server the entrypoint's `host()` starts every listener declared in
`.co/host.yaml`, so `co deploy` needs no new service unit.

The reason this is not a separate process is the reason #1310 gives for not
translating chat into `co call`: a second process would have to reach the
Agent as an OIP peer with its own key, and at that boundary the Feishu user's
identity is gone. The listener would be an admin acting on behalf of everyone
it hears from. That is the parallel authority #1310 forbids.

### 2. A listener produces one small envelope; everything else is a sidecar

```text
InboundEvent
  provider        "feishu" | "lark" | "whatsapp" | ...
  tenant          tenant_key | phone_number_id | team_id | bot id
  conversation    chat_id | wa_id | channel id
  thread          root_id | thread_ts | None
  message_id      the provider's message id — the idempotency key
  event_id        the provider's delivery id, if it has one
  sender          {id, display}      id = union_id | wa_id | user id
  text            the message body the person typed
  mentioned_bot   bool
  received_at     UTC
  raw             the provider payload, never rendered to the model
```

The model sees `text` as the user turn and `provider`, `conversation`,
`sender.id`, `thread` as structured turn metadata. It never sees `sender.display`,
`raw`, group titles, contact cards or link previews inside the prompt. This is
the Imperva lesson applied before we learn it ourselves.

Every framework surveyed that tried a rich universal schema (Bot Framework's
`Activity`, Rasa's `UserMessage`, Hubot's `envelope`) grew an escape hatch
(`channelData`, `metadata`, adapter-specific fields) and the escape hatch is
where the bugs live. The core stays at the eleven fields above. Anything a
provider adds goes in `raw` and is read only by that provider's reply code.

### 3. The principal is a triple, and it goes through the trust system

```text
principal = provider:tenant:sender.id
            feishu:tenant_key:union_id
            whatsapp:phone_number_id:wa_id
```

That string is what the trust system sees. Allowlists in `.co/host.yaml` list
principals and conversations; `strict` means the list only, `careful` means
strangers go through onboarding, `open` is refused for listeners in the first
slice. A group message is eligible only when `mentioned_bot` is true and the
conversation is allowed; membership in the group grants nothing. Messages from
this bot, and by default from any bot, are dropped before authorization.

Pairing is not a new mechanism. A stranger who messages the bot is exactly a
peer that received `ONBOARD_REQUIRED`: the bot replies asking for an invite
code, the person sends one, and `promote_to_contact` records the principal.
The first slice ships allowlists only; pairing is the second slice and needs
no new authority to exist.

Feishu's `open_id` is per-app and `user_id` needs an extra scope, so the
sender id is `union_id`. WhatsApp's `wa_id` is an E.164 number that a carrier
can reassign, so a WhatsApp allowlist entry is weaker than a platform user id;
the webhook signature is what makes it usable at all.

### 4. Stage durably, acknowledge, then run: an inbox beside the replay ledger

```text
provider event
  → verify (Feishu WS: built in; WhatsApp: X-Hub-Signature-256 over raw bytes,
    reject with 401, never 200)
  → authorize principal + conversation + mention   (in code, before the model)
  → INSERT inbox(provider, tenant, message_id, ...) ON CONFLICT DO NOTHING
  → acknowledge                                   (under 3 s)
worker, one per conversation key, many conversations in parallel
  → session_id = uuid5(ns, provider:tenant:conversation:thread)
  → claim_host_prompt(session_id, requester=principal)
  → input_handler(...)                             (same journal as POST /input)
  → reply(conversation, in reply to message_id, idempotency key = message_id)
  → mark done; ≥ 3 failures → dead-letter + one fixed apology reply
```

`.co/inbox.sqlite3` is modelled on `replay.sqlite3`: primary key
`(provider, tenant, message_id)`, `BEGIN IMMEDIATE`, bounded busy timeout, a
typed error that fails closed. Rows record `staged_at`, `claimed_at`,
`done_at`, `attempts`, `reply_id`. Retention must exceed the longest provider
replay window we accept: eight days, because Meta retries for seven.

One conversation maps to one Agent session deterministically, so a follow-up
in the same thread continues the same session and a new top-level mention
opens a new one. Within a session, work is serialized by `claim_host_prompt`
exactly as it is for OIP peers; if a second message arrives while the session
is running, it waits and is coalesced with anything else queued for that
conversation into one turn rather than run as three turns.

With `workers > 1`, one worker owns each long connection, elected with the
same lock `schedule.py` uses to pick the ticking worker. The inbox makes a
second connection harmless, but Feishu's cluster mode delivers each event to
one random client, so two connections would split the stream for nothing.

### 5. The reply goes only to where the message came from

The listener's reply function takes the conversation and the inbound
`message_id` and nothing else. It is not a general "send to Feishu" tool and it
is not exposed to the model as one. The Agent produces a result; the listener
delivers it to the originating conversation, in the thread if the input came
from a thread. Link previews are disabled where the provider allows it. This
bounds the "externally communicate" leg of the lethal trifecta to the person
who already sees the conversation.

Outbound chat tools for other purposes (#816, #1003) are a different feature
and are authorized separately.

### 6. Approval fails closed, and that is an OIP fact, not a listener fact

Today `approval_needed` binds one pending request to one session mailbox and
is answered by `APPROVAL_RESPONSE` from the peer that owns the session. A
session opened by a listener has no OIP peer. In the first slice any tool that
needs approval fails closed and the bot replies with a bounded explanation.
Chat input can never raise the session's permission mode; the Host ceiling in
DD-044 applies unchanged.

The second slice is the interesting one, and it is where this decision touches
the protocol: an approval should be answerable by any admin peer connected to
the Host, not only by the socket that created the session. That is the same
shape #1360 proposes for an encrypted approval relay. Listeners are the first
concrete reason to want it.

### 7. What this does and does not change in OIP

OIP 0.1 does not change on the wire. No new frame, no new transport value in
`OIP_COMPAT`. A listener is not an OIP peer; it is a second ingress that lands
in the same session store, the same journal and the same trust decision. The
browser continues to see listener-originated sessions in `DASHBOARD_SNAPSHOT`
exactly as it sees scheduled ones.

Three things do change beneath the wire:

- **The session record's requester becomes a principal.** Today
  `session_owner(record)` reads `record.session["requester"]["address"]`. A
  listener session has no address. The requester gains `principal` and `via`
  (`"listener"`, `"schedule"`, `"oip"`); `address` becomes optional. This is
  additive and every existing record still parses.
- **Dashboard and `co status` gain listener health.** Per listener:
  `connected | reconnecting | failed`, the last accepted event time, and
  bounded counts. Never credentials, never message content.
- **Approval ownership** is the deferred change in section 6.

## Consequences

- Feishu/Lark (#1310) is the reference implementation and its scope is
  unchanged. Its long connection dials out, so a deployed Agent adds no
  listening port. `lark-oapi`'s WebSocket client blocks, so it runs in a
  thread that does nothing but verify, authorize, stage and return; the
  three-second deadline is met by construction.
- WhatsApp (#349) uses the official Cloud API only. Its webhook is a new
  inbound HTTPS surface and is treated like a Stripe endpoint: under
  `/_co/listen/whatsapp`, signature verified over raw bytes, wrong signature is
  401, the `hub.verify_token` handshake is the only unauthenticated GET. Baileys
  and any WhatsApp Web bridge are refused, not deferred. The 24-hour customer
  service window means a reply that arrives more than a day after the message
  cannot be free-form; the listener treats that as a failure to report, not a
  template to send.
- `.co/host.yaml` gains a `listen:` section. Secrets stay in the environment
  (`FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `WHATSAPP_ACCESS_TOKEN`,
  `WHATSAPP_APP_SECRET`, `WHATSAPP_VERIFY_TOKEN`) and are never accepted on
  argv, written to project configuration or printed by `--check`.
- `docs/PRODUCT.md` §11 "Written but not wired" carries `co listen` until the
  live acceptance in #1310 passes; only then does it move to §3 and §6.
- There is still no generic listener framework. The contract above is a
  document, an `InboundEvent`, an inbox store and one `ingest()` function. The
  abstraction, if one is worth extracting, is extracted after WhatsApp is the
  second implementation, not before Feishu is the first.

## Evidence required for acceptance

Beyond the definition of done in #1310:

- **Duplicate storm.** The same `message_id` delivered fifty times while the
  model is failing produces one inbox row, one run when the model recovers,
  and one reply.
- **Crash between stage and done.** Kill the process after the inbox insert
  and before the reply; on restart the row is claimed once and the reply is
  sent once, with the same idempotency key.
- **Three-second handler.** The Feishu event handler returns within the
  deadline while an Agent turn is running.
- **Election.** `workers=2` opens one long connection.
- **Fencing.** A sender whose display name and a group whose title contain
  instructions never appear in any message the model receives.
- **Reply only to origin.** No listener test can make the reply function
  address a conversation other than the inbound one.
- **Requester compatibility.** Every existing `session_results.jsonl` fixture
  still parses after `requester` gains `principal` and `via`.

## Rejected alternatives

- **A separate `co listen` daemon that talks to the Host over OIP** — the
  listener becomes an admin peer acting for everyone; the Feishu identity is
  lost at the socket. This is the parallel authority #1310 forbids.
- **A Feishu useful tool** — tools run after input exists; a tool cannot wake
  the Agent.
- **Put the SDK inside the Agent loop** — couples reconnection to a turn; the
  connection must survive the turn.
- **Webhook first for Feishu** — needs a public HTTPS endpoint, callback
  verification and deployment routing; the long connection is the smaller
  first slice for a server behind NAT. Webhook transport can be added behind
  the same `InboundEvent` later.
- **Rich universal envelope** — Bot Framework's `Activity` and every adapter
  since grew an escape hatch. Eleven fields and a `raw` sidecar.
- **In-memory dedup** — openclaw#58611. The window must outlive the provider's
  retry schedule and the process.
- **Shared session per provider** — OpenClaw's default and its documented
  regret. One conversation, one session.
- **Baileys or any WhatsApp Web bridge** — bans on reconnect loops; the
  official API's business verification is a cost we pay once, up front, in
  parallel with the code.
- **A generic listener framework first** — seven providers, zero
  implementations. Two implementations of a written contract, then decide.
- **Chat-side approval UI in the first slice** — requires the approval
  ownership change in section 6; ship fail-closed first.
