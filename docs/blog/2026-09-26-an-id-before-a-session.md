# An ID before a session

We opened `co claude` in a new workspace and immediately handed its terminal to
O Chat. The browser looked ready: it had a Claude session ID from the
`SessionStart` Hook, a paired owner, and a Take control button. Its first
message failed without asking for the file edit it had been told to make. A
minute later the composer said the Host had not confirmed the message.

The failure was reproducible only before the first terminal turn. After a
harmless prompt in Claude's terminal, the same browser action reached the
Write approval and completed. The difference was on disk: before that prompt,
Claude had announced a session ID but had not written a resumable transcript.
Our headless browser runner treated every ID as an existing session and passed
it to `--resume`.

## The useful boundary

Happy Coder checks the native JSONL before setting the Claude SDK's `resume`
option. If the ID has no valid stored message, it starts a new query. We do not
need to copy its SDK or permission model to use that distinction. Our Station
already sees the exact native lifecycle through scoped Hooks. It now records
whether the local session has completed a turn. Handover before that point
starts a new native session for the first browser message. The new ID is then
used for later browser turns and return to the terminal. A handover with no
browser message returns to a fresh terminal instead of trying to resume the
empty ID.

There was a second boundary in the OIP path. The Host allocates a worker when
the browser sends a provider message, but that is not proof that Claude has
started. We already waited for native init and the matching SessionStart Hook
before sending a positive ACK. When native startup failed earlier, we sent no
ACK at all. The browser kept its draft, correctly, but waited for the timeout.
The worker now sends the matching negative ACK when no positive one was sent,
and the React client says Claude could not start the turn.

## What we tested

A local O Chat page in Chromium paired with a real Haiku Station in a fresh
workspace. We took control before typing any terminal prompt, sent a request
to Write a file, saw the approval card, allowed it once, checked the file's
bytes and Claude's reply, checked the narrow mobile layout, and returned
control to the terminal. The earlier failure and the fixed desktop and mobile
states are preserved in the 1.8.9b7 release evidence. The focused Core suite
passed 124 tests; the React suite passed 188.

This fixes the first-turn path, not every difference from Happy. Station's
browser approval remains deliberately limited to verified workspace edits;
Bash, MCP tools and interactive Claude questions still lack browser decisions.
We will revisit those policies when we can state and test the authority they
would grant. For this preview, the important claim is narrower: a browser can
start a real native Claude turn from an empty terminal and knows promptly if
that start fails.
