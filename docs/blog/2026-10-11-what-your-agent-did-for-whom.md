---
description: The design says a contact's request is done, not held, and the record is how the owner finds out. Before this, a contact's EXEC left no trace at all.
tags: [Trust, Approvals]
---

# What your agent did, and for whom

Today we settled how an agent decides what other people may make it do. The
answer is context over control. Most things are done and written down, and
only three kinds of action wait for the owner: credentials and money,
anything that cannot be undone, and acting as the owner in the owner's own
accounts. Aaron put it this way: if we build lots of walls, the agent is no
better than doing it by hand.

That only works if "written down" is true. So we checked it before writing a
line of policy, and it was mostly false:

- **A network EXEC left no trace at all.** EXEC runs a whitelisted tool
  directly, with no LLM, no session and no hooks. A contact could run
  `co env get` through the shipped `Bash(co *)` rule, and nothing on the
  machine would say so afterwards.
- **A tool call in a chat turn lived only in the session.** Sessions expire.
- **A trust change was written nowhere.** `co trust block 0x… --reason spam`
  printed the reason and threw it away.

## The record

Now every agent with a `.co/` keeps one append-only file,
`.co/approvals.jsonl`. It gets one line per tool call in a turn, per EXEC,
per Remote Browser request and per trust change. Each line says who asked, in
the same namespaces the rest of the design uses (`key:0x…`, `chat:feishu:…`,
`email:…`, `local`), and whether the thing was done or declined.

```bash
co approvals                       # the newest 50
co approvals --who 0x3f5a...c9e1   # one requester
```

Three things it does not do, each on purpose:

- **The agent cannot edit it.** It is a control file, like `host.yaml`.
- **It does not store secrets.** Arguments are cut to 300 characters, and
  tokens and `…KEY=` values are replaced before the line is written. The file
  can never be scrubbed by the agent, so it must never need scrubbing.
- **It never breaks the call it records.** A record that cannot be written,
  on a read-only mount or in someone else's `.co/`, is skipped. The line is
  written after the tool has run, and failing there would turn a successful
  call into an error the model might retry.

A review before merging caught the most embarrassing gap. `co ai` keeps its
identity in `~/.co`, so it wrote its record there, while `co approvals` read
the project's and reported "Nothing recorded". It now reads whichever one
exists and prints the file it read.

## Next

The record is the safety net, so it came first. The three classes come next,
decided by code from the tool and its arguments, so a turn cannot talk its way
out of one. Design: #2408, with the map of every entry path in #347.
