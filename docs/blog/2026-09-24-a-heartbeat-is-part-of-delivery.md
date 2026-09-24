# The Message Arrived. Then the Connection Lied.

The first Discord fixture looked encouraging. `MESSAGE_CREATE` crossed a fake
socket, became a message, and appeared in the queue. Then the next fixture
stopped sending events, and the listener did exactly what a naïve WebSocket
client does: it waited. Forever, politely, with nothing crashed.

That was the problem. Discord's Gateway opens with `HELLO` and a heartbeat
interval, and the client had been sending heartbeats — but the fixture never
sent back the acknowledgement. From our side the socket was open. From
Discord's side the session was already dead. An adapter that only knew how to
parse messages could pass every message test and still become a listener that
hears nothing in production.

So the unit under test changed. It stopped being "turn this JSON into a
message" and became the whole conversation: `HELLO`, Identify, heartbeat, ACK,
sequence numbers, reconnect, Resume. A missing ACK now makes the listener close
the socket itself. A reconnect keeps the session id and the last sequence so
Discord can replay what was missed, and the replay is allowed to repeat itself,
because the inbox dedupes on Discord's message id. Exactly-once is not a
promise the Gateway makes; the inbox makes it instead.

That adapter was written in early September for a package called
`connectonion/listen/`. Before it merged, the package became
`connectonion/inbox/`, and the port was supposed to be mechanical. It found two
more places where the connection could lie.

The first was the order of two lines. The old code recorded the sequence
number before it wrote the message to disk. If the write failed — a full disk,
say — the next Resume would tell Discord "I have everything up to here," and
the message that failed to land would never be replayed. Moving one line, so
the sequence advances only after the file exists, turned a silent loss into a
retry.

The second was a close code. The inbox on main now asks every listener to write
down whether it is actually connected, because `check` used to call a listener
healthy just because a process held a lock. Writing "connected" on `READY` was
easy. Deciding what to write when Discord hangs up was not. The old adapter
reconnected after every close, with backoff, forever. For a dropped network
that is right. For close code 4014 it is a disaster in slow motion: 4014 means
the Message Content intent is switched off in the Developer Portal, the single
most likely setup mistake, and no number of reconnects will switch it on. The
listener would have looked alive in `ps`, logged a reconnect every thirty
seconds, and received nothing.

Now 4004 (bad token), 4014, and the sharding and intent codes stop the listener
with exit 3 and a sentence saying which switch to flip. Everything else still
reconnects.

The lesson is the one the heartbeat taught first, repeated twice more: for an
event-driven inbox, the connection's honesty is part of delivery. A green
parser test proves almost nothing until a test also shows how the connection
finds out it has stopped telling the truth.

What the fakes cannot prove is Discord itself. No live bot has connected yet;
until one has, with the intent on, a DM, a guild mention and a forced resume,
this stays a preview.
