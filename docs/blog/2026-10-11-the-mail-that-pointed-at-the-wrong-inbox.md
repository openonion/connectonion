---
description: A co handoff sent to a Gmail address told the recipient to run co handoff inbox, which reads a different mailbox. Now co handoff open takes the saved mail itself.
tags: [Handoff, Email]
---

# The mail that pointed at the wrong inbox

The first `co handoff` that went to a real person's Gmail arrived fine. It had
the brief, the decisions, the rejected options and the base64 bundle at the
bottom. The last line said what to do next:

> Continue this with your AI: run co handoff inbox, then co handoff open ho-3116d995.

That instruction could not work. `co handoff inbox` reads the recipient's
*agent* mailbox, the `0x…@mail.openonion.ai` address every co identity gets.
The handoff had gone to `@gmail.com`. It was never going to show up in that
inbox, and the person had no co command that could open it.

## Everything needed was already in the mail

The bundle travels inside the mail body, between `BEGIN CO HANDOFF BUNDLE` and
`END CO HANDOFF BUNDLE`. Whoever received the mail already held the whole
handoff. The only thing missing was a command that would read it from there.
So `co handoff open` (and `show`) now take a file as well as an id:

```bash
co handoff open handoff.eml
```

The mail says so too: save this whole email as `handoff.eml`, or paste it into
`handoff.txt`, then run `co handoff open handoff.eml`.

## Two things the first real test caught

The unit tests passed on the first try. Then we ran the actual flow: send a
handoff to `aaron.xie@mail.openonion.ai`, save it with
`co email read 705 > handoff.eml.txt`, and open the file. It failed twice, in two
different ways.

First, the new instruction came out as "then run co handoff open ." The draft
had said `co handoff open <saved mail>`. The mail service treats anything that
looks like `<tag>` as markup and removes it. The mail now names a real file,
`handoff.eml`, and has no angle brackets in it.

Second, a later send failed with "No handoff in handoff.eml.txt". The terminal
wraps `co email read` at 80 columns, and this time the wrap landed inside the
marker: `----- ` at the end of one line, `BEGIN CO HANDOFF BUNDLE -----` at the
start of the next. The base64 was intact, since whitespace is already removed
before decoding. The marker search was the part that broke. It now accepts any
whitespace between the marker's words. The unit test that had been passing
wrapped lines by character count, which never split a word. It now wraps at
spaces the way a terminal does, and it splits the marker on purpose.

A downloaded `.eml` raises one more case. Its text part may be
quoted-printable (which turns the `=` of base64 padding into `=3D`) or base64
from top to bottom. If the file has MIME headers, we decode the plain-text
part before looking for the bundle. If it doesn't, we search it as it is.

## What it took

The handoff was in the mail from the start. The fix was to make `open` read it
from wherever the mail ends up, and to make the mail's instruction one that
actually works. The unit tests checked the logic. The two bugs above only
showed up when a real mail went through the mail service and a real terminal.
