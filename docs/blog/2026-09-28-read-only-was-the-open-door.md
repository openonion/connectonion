# Read-only was the open door

Someone running a hosted agent in a Feishu group did the careful thing: they
switched the session to read-only. Then a chat message led the agent to run a
CLI that nothing had granted, and it ran. Read-only had let it through.

The reason took one line to find. When a tool call is not granted, the
approval hook asks a person. A chat turn has no person on the other end: no
approval dialog, no IO. The hook's answer to "there is nobody to ask" was
`return`. In Auto mode a policy runs first and decides everything, so the
early return was harmless there. Read-only skips that policy, so nobody was
asked and everything ran. Our most cautious mode was the least safe one.

The same report had two more findings. `allowed: false` in `host.yaml` did
nothing, because the matching loop skipped any entry that was not allowed. An
operator who wrote a deny believed it held. And in Auto, a command the policy
had no rule for ran as "ordinary command, allowed by default". That was right
for the operator's own nightly jobs, which was why we chose it. It was wrong
for a turn that anyone who can @-mention the bot can start.

A second report was worse. A chat-driven turn was refused a script, and the
refusal helpfully said a permission could also be declared in the skill's
`SKILL.md` frontmatter. So the model edited the frontmatter, and Auto approved
that as a reversible workspace edit. The hint written for the operator had
become the agent's instructions.

Now there are four rules, and each has a test that failed first:
- With nobody to ask, an ungranted call is refused in every mode.
- A chat turn gets no default allow.
- `allowed: false` denies, even inside `a && b`, and a deny beats any allow.
- Writing a skill's frontmatter is granting, so a chat or unattended turn
  cannot do it, and with a person present it is always a real prompt.

The refusal text still tells the operator what to add to `host.yaml`, and it
says that change is the operator's to make.

The lesson: every message a model can read is an instruction to it. A
remedy written for a person has to say who it is for.
