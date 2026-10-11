---
description: 1.9.2b14 ships the record before the rules. A contact's request is done and written down; three kinds of action wait for the owner.
tags: [Release, Trust]
---

# 1.9.2b14: the record comes first

This preview answers a question that will matter more each week: when other
people's agents ask yours for things, how do you know what it did?

We chose not to start with rules. If the agent has to ask the owner before
every small thing, it is slower than doing the work by hand. So the default is
to act and write it down, and the first thing we built was the writing down.
`co approvals` lists what your agent did, for whom, and whether it was done or
declined. That covers turns, direct tool requests, Remote Browser and every
change to who may reach it.

Then the few things that should not just happen. Credentials and money,
anything that cannot be undone, and acting as you in your own accounts now wait
for you when someone else asked and nobody is there to ask.

The release check ran it from the wheel. A chat sender asked for an API key and
was told it needs the owner. A plain `echo` from the same sender ran. Both are
in the record, and the refusal is filed under `credentials`.
