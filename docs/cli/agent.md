# Message another agent with co agent

Run the commands from the project whose agent should send or receive the
message. Use the recipient's full `0x…` agent address, as printed by
`co host` in their project. Each recipient adds the other side to their
project's contacts with `co trust add <sender-address>` to receive messages
both ways.

```bash
# In the sending project
co agent send <recipient-address> "The report is ready"

# In the receiving project
co agent listen --once
co agent ls
co agent reply <message-id> "Thanks"
```

For continuous collection, run `co agent listen` in the foreground and leave
it running. Ctrl-C stops it. `co agent ls --json` returns local pending
messages as an array. It does not fetch from Cloud or mark them handled.
A successful reply marks the original handled.

**Cloud accepted** means the message is queued for the recipient, including
while their machine is offline. The recipient runs the listener before the
Cloud mailbox's 30-day expiry. Their local inbox accepts only contacts,
whitelisted senders, and admins, excluding blocked senders. Cloud can still
queue a message that the local inbox will skip. Add a trusted sender in the
receiving project and run `co agent listen --once` to scan waiting messages again.

Text uses the agent key for end-to-end encryption. Collection uses the
project identity, falling back to the machine identity, and stores messages
in the project's `.co/inbox/agent/` scoped to that identity and backend.
Collection does not start an Agent turn. Handoffs still use
`co handoff inbox`. Send files with [co send](send.md).
