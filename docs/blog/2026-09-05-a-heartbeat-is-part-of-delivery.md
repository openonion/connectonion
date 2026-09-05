# The message arrived. Then the connection lied.

The first Discord fixture looked encouraging. `MESSAGE_CREATE` crossed the fake
socket, became a seven-field message, and appeared in the mailbox. Then the next
fixture stopped sending events. The listener did exactly what a naïve WebSocket
client does: it waited forever.

Nothing had crashed. That was the problem.

Discord's Gateway had sent `HELLO` with a heartbeat interval, and the client had
sent heartbeats, but our test never returned the matching acknowledgement. From
the application's point of view the socket was still open. From Discord's point
of view the session was no longer healthy. A parser-only adapter could pass every
message fixture and still become a silent listener in production.

That changed the unit under test. It was no longer “turn this JSON into a
message.” The fixture had to walk through `HELLO`, Identify, heartbeat, ACK,
sequence updates, reconnect, and Resume. When an ACK is missing, the listener
now tears down the stale session. When Discord asks it to reconnect, it keeps the
session id and last sequence number so the resumed stream does not start from an
invented point.

The same test exposed another boundary. Replaying a dispatch after reconnect is
normal, so Gateway recovery cannot promise exactly-once delivery. The durable
local mailbox owns deduplication instead. The adapter can reconnect aggressively
without making a second message actionable.

That was the useful turn: heartbeat handling is not connection housekeeping.
For an event-driven inbox, it is part of message delivery. A green parser test
proves almost nothing until the test also shows how the connection discovers
that it has stopped telling the truth.

The preview still needs a live bot with Message Content intent enabled before it
can lose that label. The fixture proves the state machine we control; it does not
pretend to prove Discord account configuration.
