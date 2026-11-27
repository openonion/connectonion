---
title: An agent can leave a message
status: draft
---

A laptop agent needs to tell an office agent that the report is ready.
The office computer is asleep. The sender knows its agent address and
can leave a message now. The recipient collects it when the computer is
back, and decides when to reply.

ConnectOnion already has two relevant pieces. Handoffs can wait in a
Cloud mailbox, and Feishu and WhatsApp listeners put messages into a
local queue independently of the agent that reads it. Agent messages
use the same mailbox and queue, with the project key sealing the text
to the recipient. A message has its own type so the handoff reader can
keep its existing workflow.

A direct socket could deliver in real time while both sides are online.
It would still need another way to deliver when a machine is asleep.
Using the mailbox for both cases gives a simple first version, at the
cost of polling latency and Cloud holding pending messages. The
listener revisits earlier rows because two database transactions can
commit in a different order from their allocated IDs.

The listener checks the local trust list before putting a message in
the local queue. The CLI reports when Cloud accepts a message. The
recipient chooses when to reply, and the receipt for local delivery
can be added when it has a user-facing use.
