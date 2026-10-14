# Trust starts from cost

Status: accepted (owner, 2026-10-14). The handoff default below ships in 1.9.2b31; the judging Trust
Agent is #2407, enforcement on the Host #2401, the three special classes #2408.

## The owner's words

> 我们需要根据和对方的联系情况（比如有没有 email 的往来、是否知道对方的个人信息等）来确定赋予的权限。
> 其实我们信任的第一选择就是"代价"，只有了解了对方是谁、我们和对方的联系是什么，才能确定给他什么权限。
> 权限分配是跟我们的 REM 等系统联动的……让智能去判断我们要给他们什么权限。

## Decision: the first principle of trust is cost

How much we let someone do through our agent follows from **what it would cost them to abuse it**,
and we can only know that cost once we know who they are and what ties us. A colleague or a partner
has a working relationship, a reputation with us and often an agreement to lose; a student has a
course and a teacher; a stranger with no record here loses nothing. So:

| Who they are to us | What the evidence looks like | What they may do |
|---|---|---|
| **Stranger** | no co rem page, no mail between us, no prior handoff | exchange messages about the one handoff they are part of; nothing on our agent |
| **Student** | a co rem page that says so; course or supervision mail | the above, plus talk to our agent with work context; no commands, no browser |
| **Colleague or partner** | a co rem page with a shared organisation or deal; a long two-way mail history; an agreement | the above, plus reading named project paths and running named tools, each recorded |

Whatever the tier, three things always wait for the owner (#2408): credentials, authority and money;
irreversible deletes and overwrites; acting as the owner in the owner's own accounts.

## How it is decided

- **The evidence is what co rem already knows:** the person page, the mail between us, the
  organisation, earlier handoffs. A Trust Agent reads it and sets the grant for that one identity,
  with the evidence it used, and the record says so (#2407: one grant file per identity, ceilings by
  how strong the identity is: a signed key can reach `run`, an email address at most talk + context).
- **Context over control (DD-076), applied to people:** the agent judges from context and records
  what it did, instead of asking the owner for every small grant.
- **The owner's own entries win.** An entry the owner set is never changed by the AI.
- **No evidence means the stranger tier.** Cost cannot be known for someone we know nothing about,
  so it is assumed to be zero.

## What this means for handoff today

A handoff is often the first contact with someone, and until the Trust Agent of #2407 reads co rem
there is no judge. So both sides of a handoff hold each other at the stranger tier (`handoffs`):
messages about that handoff, nothing more. Before 1.9.2b31 the acceptor became a full contact of
the sender's agent, which under `careful` drives that agent and approves its own tool calls; and the
acceptor is whoever opened the page link first. Raising someone is the owner's `co trust add` until
the Trust Agent can judge it from co rem.

## Why not trust by default and take it back later

A grant that turns out wrong has already been used: a contact can run commands as the owner before
anyone notices. Starting from what the evidence supports costs a known person one step; starting
high costs the owner whatever a stranger chose to do.
