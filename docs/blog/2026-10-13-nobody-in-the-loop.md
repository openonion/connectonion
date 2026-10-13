# Nobody in the loop

*2026-10-13*

We ran two handoffs end to end on 1.9.2b19: a Claude Code session on a Mac
sending, Codex on Linux receiving from an empty home directory. The work came
out right both times. What we watched was where a person had to step in.

The first handoff stopped twice for the person. Codex had installed co and
saved the brief, then asked them to paste a 110-character `co handoff accept`
line into a terminal, though its network was on and it could have run it
itself. The prompt told it to: "in a sandbox ask me to run it", and "ask me
before you change any file". An agent that follows instructions follows those
too.

Then it finished, and had no way to say so. It asked the sender how to return
the patch, got pointed at the session copy, and mailed the patch with
`co email send`, outside the handoff. The sender's `co handoff status` still
said "Accepted". The second handoff, between agents that were already
contacts, reached only the other agent's inbox: the person was never told it
existed.

1.9.2b20 takes the person out of those places. The agent accepts by itself,
does the work in the folder it was given, and asks only before something that
cannot be undone or that leaves the machine. When it is done it runs
`co handoff done <code> "what I did" --file result.patch`, and the sender's
status shows "Done" with the file saved next to the handoff. A handoff to a
contact is mailed to the person as well as put in their agent's inbox. The
preview now warns when the code is not pushed, because the recipient cannot
fetch it, and lists every private detail instead of the first ten.

What the agent still may not do is treat the brief as orders. It is the
sender's text; the person who pasted it is the only one who can override it.
