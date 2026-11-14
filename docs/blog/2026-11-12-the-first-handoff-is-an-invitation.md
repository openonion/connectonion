---
title: "The first handoff is an invitation"
date: 2026-11-12
description: A month-old pull request for the first handoff email never merged. Most of it had been overtaken by a better mail; one test had not.
tags: [Handoff, Onboarding, Tests]
---

# The first handoff is an invitation

In October someone received a handoff and could not find the first thing to do.
The email looked like a Markdown file poured into an inbox: a long prompt,
install branches for three Python tools, and a block of encoded data. Pull
request #2417 fixed that. It put the sender, the task and one labelled block
to paste first, hid the encoded bundle, and taught `co handoff open` to look
in a saved mail's HTML part as well as its plain-text part. The release notes
for it reached `main`. The code never did.

When we came back to land it a month later, the mail it fixed was gone. The
handoff now arrives as a short note in the sender's own voice, from their own
mailbox, with a button to a web page and one line to paste. The installer it
proposed, `install.sh` pinned to a release, is how every recipient installs co
today, fetched from the release tag rather than from `main`. Porting the old
`to_mail` layout would have brought back a design the team had already
replaced, twice.

So we read the old diff line by line against what `main` does now, and asked
of each change: is it missing, and is it still right? Almost everything was
already there in a better form, or no longer true. The documentation's
"COPY FROM HERE" block, for one, names a label no mail carries any more.

One idea survived the redesign without a guard. The note's plain-text part
leaves the bundle out on purpose, because a plain-text reader showed it as a
wall of base64. The bundle now lives only in the HTML part. That makes
`saved_mail_text`, which joins both parts before `co handoff open` looks for
the bundle, quietly load-bearing: if it went back to reading only the plain
part, a mail saved from Gmail as `.eml` would stop opening, and no test would
notice.

The test from #2417 covered exactly that case, for a mail that no longer
exists. We rewrote it for the note that does: a saved mail with only an HTML
part, and a multipart mail whose plain part has no bundle, must both open and
verify, and the paste block must come back word for word. We checked it can
fail by narrowing the parser to the plain part; it did, and passes again on
the real code.

The lesson is about old branches more than email. A pull request that sat for
a month is not a patch to apply; it is a list of claims to re-check. What it
knew about the problem can outlive what it did about it.
