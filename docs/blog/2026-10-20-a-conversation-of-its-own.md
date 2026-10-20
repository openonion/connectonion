# A conversation of its own

*2026-10-20*

Ody handed Aaron a pricing discussion. Aaron had a Claude Code session open, the one he'd been using for
marketing all day, so he pasted the line there. The line said "do what it says, here in this folder", and
`co handoff accept` agreed: "Do the work now, here." So a Mac mini rental quote got worked out inside a
marketing conversation, in a repository it had nothing to do with. Meanwhile, the session `accept` had just
built for it, with Ody's whole conversation already loaded, sat unopened at the bottom of the output.

The obvious fix was to always send the work to that session. But that would add a step to every handoff
pasted correctly, into a new conversation, to save the ones pasted wrongly. The agent that reads the line
already knows which case it's in. It can see whether its conversation had anything in it before the paste.

So the prompt now asks it first. If this conversation had other work in it, don't start: tell the person
to paste the line into a new conversation, or give them the line that opens the sender's own, and stop.
A handoff with no repository also stops writing into whatever project the folder holds. It makes its own
folder there.

We checked it with a real Claude Code. It wrote a two-line poem about rain, and then got the handoff in
the same conversation. It fetched the page, stopped, and said why: no install, no accept, nothing sent.
The same line in a fresh conversation went straight to work.
