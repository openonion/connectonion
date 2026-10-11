---
description: Asking permission for every small thing teaches people to click yes. The agent now acts, writes down what it did and for whom, and holds back only three kinds of action for the owner.
tags: [Trust, Approval, Design]
---

# Three things only the owner decides

An approval dialog that opens for every command does not make an agent
safe. It makes the person in front of it tired. After the tenth
`npm install`, they click yes without reading, and the eleventh dialog,
the one that mattered, gets the same click.

We kept adding gates anyway. Every time something went wrong, the fix was
a new place to ask. The result was an agent that interrupted its own owner
for small things and still had paths where nobody was asked at all. Our
direct tool-execution path, for example, never opened a dialog: it checked
a whitelist and ran the tool.

So we changed the question. We stopped asking "should this be allowed?"
and started asking "what will the owner want to know afterwards, and what
must they decide themselves?" We call this context over control.

## Most things: act, and write it down

When someone else drives the agent, through the host, a chat inbox or a
direct EXEC call, every tool call now leaves one line in
`.co/decisions.jsonl`:

```json
{"at": "2026-10-11T09:14:02+00:00", "path": "exec", "requester": "0x3f…", "level": "contact",
 "tool": "bash", "args": {"command": "pytest -q"}, "outcome": "executed", "reason": ""}
```

The line says who asked, at what trust level, what ran and how it ended.
Refused calls are recorded too, so the owner can also see what was
attempted. Arguments that look like secrets (`password`, `token`,
`api_key`) are replaced, and long values are cut. The file is safe to read
and safe to share.

The agent's own tools cannot edit this file. It sits on the same protected
list as `host.yaml`, now joined by the trust lists (`contacts.txt`,
`whitelist.txt`, `blocklist.txt`). A record the actor can rewrite is a
diary, not a record.

## Three things: the owner's own say

Some actions cannot be undone by reading a log the next morning. The owner
drew that line, and it has three parts:

1. **Credentials, authority and money.** Revealing keys, changing who is
   an admin or a contact, transferring credits, creating a paid server.
2. **Irreversible deletes and overwrites.** `rm -rf`, `git push --force`,
   deleting a remote branch, destroying a server.
3. **Acting as the owner in the owner's own accounts.** Sending mail from
   their Gmail or Outlook. The agent's own mailbox (`co email`) is not on
   this list, because it speaks as the agent, not as the owner.

Code decides the class, never the model. `special.py` reuses the effect
classes the auto-approve policy already assigns, so there is one
classifier rather than two that slowly disagree. It also checks a shell
chain one segment at a time. The policy reports a chain by its first
segment that needs approval, so in `python job.py && co transfer 5 0x…`
the transfer used to hide behind the script. Here the most serious segment
decides.

For now, a remote caller below admin who reaches one of these classes gets
a plain answer: this needs the owner, ask them to run it from their own
terminal. That holds on every path, both the agent's turn and direct EXEC,
before the whitelist and before the approval dialog. So no `host.yaml`
rule, and no "yes" clicked by the caller in their own session, can grant
it. The owner, working at their own terminal or connected as admin, runs
these as before, and the line is still written.

## What comes next

Declining is the temporary half. In the next steps of #2408, the agent
will email the owner's operator addresses from its own mailbox and say
what it wants to do and why. The owner replies `yes`, `no`, or `always`.
A routine request then becomes a standing authorization, and the owner
does not have to answer the same thing twice. After that comes a daily
digest of the record with an undo link.

The aim is that someone else working with your agent is never blocked on
small things, and you are never surprised by a large one.
