# The connection came back alone

The listener reconnected. A new test message arrived, and the command replying to
it worked. Those were reassuring observations until we looked for the message
sent while the listener was disconnected. It was still visible on the provider,
but absent from the local inbox 175 seconds after reconnect.

The experiment interrupted only the test listener's socket for 135 seconds,
longer than its 120-second heartbeat. We had expected the provider to replay the
gap. The successful connection told us nothing about whether that replay happened.

Adding another retry to connection setup would repeat the part that already
worked. The missing operation was a comparison: what did the provider retain
that the mailbox had not recorded? The proposed repair reads history for known
conversations and sends those records through the existing delivery function.
A message that arrived live, was claimed, or was completed stays deduplicated.

The tempting shortcut was to advance the history timestamp after each request.
That fails halfway through a paginated response: a later page can fail after the
checkpoint has passed messages on it. The checkpoint now moves only after the
whole reconciliation succeeds. A regression test interrupts the second page,
opens a fresh recovery instance, and verifies that the earlier boundary survives.

History also exposes a different boundary. It may contain group discussion that
was never addressed to the bot. Recovering that discussion as new agent work
would change the meaning of receiving a message. Group recovery therefore checks
for this bot's mention, and it only visits conversations already known locally.

These are offline results for the repair, not a claim that the live failure is
fixed. Repeating the real gap test requires authorized history access. Until that
observation exists, the release gate remains open: a connection coming back is
only the beginning of recovery.
