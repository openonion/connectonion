---
description: The record wrote down that a handoff made someone a contact, but not which handoff. Now both sides record the handoff id.
tags: [Handoff, Trust]
---

# Why is this agent a contact?

1.9.2b14 started keeping a record of every change to who may reach an agent.
On the first real run, a handoff from this Mac to Parrot added each agent to
the other's contacts. The record caught it:

```
{"path": "trust", "subject": "key:0x21cd…5a1a", "tool": "add to contacts", "decision": "done", "reason": null}
```

The entry has a who and a what, but no why. A contact can use the tools your
Host pre-authorises, so "why can this agent do that?" is the first question the
record gets asked. `null` is no answer.

The why was known all along. The sender's side knew which handoff the other
agent had accepted, and the recipient's side knew which handoff it had just
taken. The handoff id was simply never passed down to the line that writes
the record.

Now each side writes it:

```
"reason": "sent us handoff ho-c9a0a0d3"        # on the recipient's side
"reason": "accepted our handoff ho-c9a0a0d3"   # on the sender's side
```

`co approvals --who key:0x…` now answers the question. `co handoff status
ho-c9a0a0d3` shows the rest: what was handed over, and when it was accepted.

The test that pins this ran a real accept and a real status on both sides. It
failed on main with `None` where the reason belongs.
