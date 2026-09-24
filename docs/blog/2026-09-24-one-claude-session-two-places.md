# One Claude session, two places to work

The first version of our Claude Code Work Room began when a ConnectOnion Agent
called Claude as a tool. That was useful for delegation, but it did not answer a
more ordinary request: someone had already started Claude in a terminal and
wanted to open that exact session on a phone. The tool call could start a new
turn; it could not own the terminal's session or hand it back.

`co claude` now starts Claude's normal terminal alongside a private OIP Host.
Claude's session Hook identifies the session and the transcript to follow. The
Host reads only that transcript for visible messages and turns bounded Hook
facts into OIP activity. A browser first passes the Host invite gate, then
claims the session with the pairing code printed in the terminal. A signed
control command stops and reaps the terminal writer before the browser can send
a direct Claude message. Returning control waits for that headless turn to
finish and starts the terminal with the same session ID.

The writer boundary is the important part. Watching progress can happen from
multiple screens; writing cannot happen from both at once. A lock covers the
workspace while either Claude process owns it, including the instant before a
fresh terminal has reported its session ID. The browser's control state is a
revisioned OIP event, so a stale click cannot silently take a newer owner's
turn. Unpaired session history is private to a sentinel owner and is absent
from ordinary session listings.

A real local test used Claude Haiku. The terminal answered a prompt, the O Chat
browser paired and took control, a browser message resumed the same session,
and control returned to a live terminal showing that message and answer. The
first return attempt had exposed a race: the answer was visible before the Host
had marked the direct turn done. The return path now waits for that durable
completion. The browser path was run again end to end after the fix.

The beta still requires the terminal process to remain running. It does not
turn Claude into a detached service after `/exit`. Browser file edits use a
scoped owner approval; commands and unknown actions are denied. The file-edit
Hook response has a focused test, while a live file-edit approval remains a
separate acceptance step. Those limits are part of the preview, not hidden
behind a green mock browser test.
