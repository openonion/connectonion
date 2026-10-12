---
description: A handoff announced a new contact and pointed to co trust list, which could not see it from a project folder. co trust list --global shows the identity co ai and co handoff use.
tags: [Handoff, Trust]
---

# The contact we pointed at

After a handoff is accepted, both sides are told:

```
… is now your agent's contact parrot (co trust list); co handoff send parrot reaches them again.
```

On today's Mac → Parrot run we did what it said, from the project folder the
handoff came from:

```
No agent here — …/log-pruner/.co does not exist.
```

Both halves are true. `co handoff` works as the global identity in `~/.co`,
which is the one `co ai` uses. `co trust list` reads the agent in the current
directory, because trust lists belong to one agent: two agents on one machine
used to share one whitelist, and that was a real bug. So the contact had gone
where it belonged, and we pointed at the place it does not live.

The fix is to say which agent:

```
co trust list --global
```

It shows the global identity's lists. The handoff messages now point to it.
In a folder with no agent, `co trust list` mentions it. The Contacts section
no longer says "verified via invite/payment" about someone who came in by
handoff; it says invite, payment or an accepted handoff.

The deeper problem stays open. Who someone is to the owner is spread across a
dozen stores, and #2407 replaces them with one grant file per identity. Until
then, a message that names a command should name the one that finds the
thing.
