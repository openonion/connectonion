# A Session ID Is Not Browser Authority

*2026-08-26*

The first Remote Browser sketch worked in one terminal. We sent a remote shell
command to `co browser`, it opened a tab, and it printed an identifier. For a
demo, that looked finished.

Then we opened a second terminal.

The first connection was gone, so the next command had only the printed
identifier. If we accepted it, anyone who copied the identifier could control
the tab. If we rejected it, the original caller could not reconnect. A Host
restart made the problem worse: the browser daemon could still be alive while
the shell command had left no durable record of who owned its tab.

The identifier told us which browser object we meant. It told us nothing about
who had authority over it.

## The turn was deleting the exciting command

Our first instinct was to keep the demo and add checks around it. Instead, we
removed navigation and wrote the ownership test first: Alice starts a session,
Bob obtains its ID, and Bob asks for status, diagnosis, and stop. Every answer
must look exactly like a nonexistent session. Alice reconnects through a new
Host service instance and still sees her session. Repeating the same Start must
not open a second tab; repeating Stop must not fail or close something else.

That test forced the protocol to carry less authority, not more data. The Host
takes the owner from the authenticated OIP connection. There is no owner field
in the request for a caller to spoof. The session ID only locates a private
registry record after the owner matches. The record survives a Host restart and
maps to a named tab in the existing browser daemon, so Remote Browser does not
quietly become a second driver.

Only then did the original one-terminal demo become a real lifecycle:
start, list, inspect, diagnose, stop, disconnect, and reconnect.

## The next shortcut failed for the same reason

With ownership fixed, adding `open` looked trivial. It was not. Checking the
first URL would still allow a redirect to a private address, a hostname to
resolve differently on the next request, or a public page to fetch private and
link-local subresources. An allowlist at the CLI boundary would make the demo
look safe while the browser crossed a different boundary underneath it.

So diagnosis now reports navigation as unavailable. Relay control also fails
closed: a signed OIP command authenticates its caller, but without the reviewed
secure channel it does not hide browser-control plaintext from the Relay.

The useful lesson came from that second terminal. A session ID is a reference,
not a capability. Once we treated it that way, retries, reconnects, restarts,
and refusals became part of one authority model. Navigation can arrive later,
after its whole network path—not just its first URL—can enforce the same kind of
boundary.
