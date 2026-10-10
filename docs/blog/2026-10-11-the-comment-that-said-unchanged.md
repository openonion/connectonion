---
description: A comment in address.py still said the agent identity was the bare seed[:32] slice, "unchanged", a year after SLIP-0010 replaced it. We removed it and the pointer to a command that no longer exists.
tags: [Identity, Docs]
---

# The comment that said "unchanged"

ConnectOnion used to turn a recovery phrase into an address with one line,
`SigningKey(seed[:32])`. It matched no standard. #404 replaced it with
SLIP-0010, which re-keyed every address once, and #1015 recorded the rest of the
decision: the old derivation is not coming back, and the migrate path that
carried accounts across that gap goes too.

The code followed. The comments did not, at least not all of them.

## Two comments, one wrong turn

The top of `address.py` tells the story correctly: identity *used to be* the
bare slice, and here is why it stopped. Scroll down four hundred lines to the
SSH section and you find this:

```
# The agent key is deliberately left on its original derivation — bare
# seed[:32]. Deriving it differently would change every existing agent's address
#
#     agent identity : SigningKey(seed[:32])                     (unchanged)
#     ssh access     : SLIP-0010, one path per server            (#427)
```

It was true when it was written. The SSH work in #427 came first and was
careful not to touch the identity. Then #404 touched the identity, and nobody
went back to the paragraph that promised it would never move.

The result is a file that contradicts itself. A reader who arrives at the SSH
section first, which is where you land when debugging a deploy, learns that
the identity is the raw slice, and "every address question has to ask which
kind first" is back, the exact confusion #1015 was filed to end.

The second one was smaller. A docstring in the deploy code explained a billing
mismatch "after `co account migrate`". That command is gone. Someone reading
it would go looking for it.

## Keeping it from drifting back

Both comments now describe what the code does: identity and SSH keys come off
one SLIP-0010 tree at different SLIP-0013 paths. A small test walks the
package source and fails on a line that calls `seed[:32]` the current or
"unchanged" derivation, or that points at `co account migrate`. It failed on
main with both lines found, and passes now. The history paragraphs that say
"used to be" stay. They are the reason the new scheme looks the way it does.
