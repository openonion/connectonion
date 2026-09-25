# Two Version Numbers We Gave Back

The question was meant to take five minutes: what is in 1.8.8?

`docs/roadmap.md` said the current milestone was 1.7.0 — a preview train that
finished weeks ago. VERSIONING.md, which is scrupulous about what shipped, says
nothing at all about what has not. The GitHub milestones had the answer, except
the milestone named *1.8.6 — WhatsApp, Discord and Telegram mailbox adapters*
contained an issue whose first line says those adapters moved to 1.8.8, and the
milestone for the version they actually moved to did not exist, because the
person moving them could not create one.

So three documents, three answers, and the true one was in a header paragraph
somebody had written by hand on top of a superseded plan.

The obvious repair is to fill the roadmap in: put the adapters under 1.8.8, put
the notice-things-by-yourself work under 1.8.9, and give every number a row. We
started doing that. What stopped us was reading why 1.8.9 said 1.8.9. The issue
explains itself honestly — *1.8.5 is in beta with one live gate outstanding, and
1.8.6 is three chat adapters that must not change the verb contract* — and every
clause of that reasoning had since expired. 1.8.5 shipped. 1.8.6 stopped being
three chat adapters. The number was still there, holding a place in a queue that
no longer existed.

That is what a version number does when you assign it to work nobody has
started. It stops being a plan and becomes a promise about ordering that the
next decision quietly breaks, and the breakage is invisible because nothing
fails — the issue just sits there, labelled, wrong.

So the roadmap now has two versions in it with nothing scheduled, and says so in
those words: *work gets a number when somebody is about to do it.* The next
release is the Personal Wiki, which is the kind of thing that takes as long as it
takes; anything we scheduled behind it would be a date nobody could keep. 1.8.8
and 1.8.9 are whatever the two releases after it turn out to be.

The adapters got a real number — 1.9.1, after the sender allowlist rather than
before it. That ordering is the one piece of this that is an engineering
decision rather than bookkeeping. Each adapter opens a new `co <provider>`
surface that anybody in the room can command, and 1.9.0 is where the Host learns
which senders it will answer. Three more open doors and then locks fitted to all
of them is more work than the lock first.

This repo's versioning rules already said the thing we relearned. *A whole
number is earned, never reached.* We had been applying that to 1.9.0 and 2.0.0
and not noticing it applies just as much to 1.8.9 — a patch number handed out in
advance is the same bet on a future you have not lived through yet, just a
cheaper one.
