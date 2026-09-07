# Codex Was Ready. Codex Had Never Opened.

The request was unambiguous: open Codex.

The browser replied, “understood, I'll open the codex for you right away.” A
shell card ran `pwd && ls -la`, another ran `which codex`, and then the page
announced that Codex had been initialized. It even printed a session ID.

Only one detail was wrong: none of that work came from Codex.

The model badge still named the base model. The commands were ordinary parent
agent tools. The confident completion message was prose assembled around them.
When another path tried to reach the intended provider, it ended with the much
less polished truth:

```text
misconfigured: [Errno 2] No such file or directory
```

At first this looked like executable discovery. `which codex` succeeded, so we
checked PATH inheritance and subprocess environments. That explained how a
missing binary *could* produce the error, but not why the browser had already
declared success or why the wrong model was doing the work.

## Following the card backwards

We started at the visible lie and traced it down the stack.

O Chat rendered the event it received. React had decoded the connection it
selected. The Host had accepted the session. `co ai` had given the parent agent
several ways to interpret “open Codex”: a native provider tool, a generic
coding-agent edge, and an alternate protocol route left over from the previous
preview. A fallback could keep the conversation moving after the selected
provider path failed. From the parent model's perspective, running a shell and
answering helpfully was progress. From the user's perspective, it was the
opposite of the requested product.

The file-not-found error and the fake success were the same bug at different
layers. Too many components could decide what “Codex” meant, and none owned the
whole promise visible in the card.

The turning point was to stop improving fallback. A clearer fallback would
still be a different agent wearing the requested provider's name.

## Removing a path made the system more capable

We gave the browser one boundary. OIP carries the authenticated session,
messages, tool activity, cancellation, failure, and reconnect. React owns that
state, and O Chat renders it.

We gave each coding provider one native adapter. The Codex tool owns Codex
launch, authentication, sandbox and approval selection, native events, and its
canonical session ID. Claude Code owns the corresponding Claude details. They
translate activity into OIP, but neither can silently become the parent model
or a generic child.

Now a missing provider fails before a session is celebrated. The error names
the adapter and the installation action. When the Codex card says running, a
Codex process produced the event. When it says completed, the final result and
session ID came back through that same adapter.

We replayed the original journey instead of trusting the new abstraction. The
card was captured while running, expanded after completion, forced through a
real failure, and viewed at phone width. Then the built wheel was installed in
an isolated environment so a source checkout could not rescue a broken
package. Those checks mattered because the original bug also looked correct
from every layer tested alone.

The lesson was not that fallback is always bad. It is that provider identity is
part of the result. If someone asks for Codex, a useful answer from something
else is still a failed handoff. The honest system has fewer ways to say yes.
