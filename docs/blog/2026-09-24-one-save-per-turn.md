# One save per turn, not one per tool call

`co claude` shipped in 1.8.8b4. It lets you watch the Claude Code session in
your terminal from a browser, and hand it back and forth. On review, the file
that remembers the session turned out to grow with the square of its length.
A thousand tool calls, which is an ordinary afternoon for Claude, left a
769 MB file behind.

The cause was one line doing something reasonable in the wrong place. Our
session store never edits a line; it appends a fresh copy of the whole session,
and the last copy wins. That is cheap when you save once per turn, which is
what every other part of the Host does. The new Station saved on every Hook
event instead, so the thousandth tool call rewrote the previous 999 as well.

The tempting fix was the one Happy Coder uses: a separate event log where each
event is its own numbered line. It is the right shape for their sync server.
For us it would have meant a second storage format, a second reader for
history and reconnect, and a migration, all to fix one component that had
simply stopped following the house rule. So the fix makes Station follow the
rule. Events of the current turn wait in memory. The browser still sees them
live, because the watcher reads the saved history plus that in-memory tail.
They are written together when the turn ends or when control changes hands.
Station got shorter, and the watcher no longer reaches into storage.

The same review removed a cap that would have bitten later. After 4,096 Hook
events the receiver refused everything, including permission requests, so a
long session would quietly stop mirroring and every approval would be denied.
The cap is gone, and approvals are now exempt from the per-second rate limit.

What we did not fix is worth saying too. Saving per turn is 18 times smaller,
but it is still quadratic across turns, and that is true of every Host session
today. That belongs in the session store itself, with its own issue, and not
as a special case bolted onto Claude.
