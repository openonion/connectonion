# A skill nobody mentioned

The benchmark was supposed to answer a simple question: when a reimbursement
request comes in, does the Agent reach for the `reimbursement` skill? The
project had the skill in `.co/skills/reimbursement/SKILL.md`, the Agent had
the `skill` tool and the skills plugin, and `co eval run --invoke auto` sent
five real cases to `co/gemini-3.8-flash` on 24 September.

Five out of five failed the same way: "the Agent never called
skill(name='reimbursement'); tools it did call: ['submit_invoice']". The
model went straight to the tool it could see and answered from what it
already knew. It was tempting to read that as a weak model, or a skill with
a bad description, and start rewriting the description.

The description was never the problem, because the model never saw it. The
plugin discovered every skill at startup and stored the list on
`agent.skills`, and that is where the list stopped. A few hundred lines
further down the same file sat a function written to append that list to the
system prompt, complete with a careful instruction ("your first action is
`skill(name=...)`") that had been tuned after an earlier agent went hunting
for skill files with glob. It even had its own tests. Nothing called it.
`co ai` hid the gap: it builds its own skills section from project context,
so every agent anyone looked at closely was told its skills, and only the
plain `Agent(..., plugins=[skills])` a user writes by hand was left in the
dark (#1666).

The fix is one call: when the plugin sets up, it appends the list to the
Agent's system prompt, so every session starts with it, including the fresh
session the benchmark opens for each case. If the prompt already has an
`# Available Skills` section, as `co ai`'s does, it leaves that one alone
rather than listing the same skills twice.

The test that proves it uses a fake model that is only as smart as a real
one is allowed to be. It reads the messages it was sent and calls
`skill(name='reimbursement')` only if they name that skill and its
description. Before the fix, it never called it and the benchmark failed; now
it does and the benchmark passes.

The lesson is about what a test of a helper proves. The injection function
was tested and correct; its tests said nothing about whether anyone used it.
The test that would have caught this asks the question from the model's
side: given only what you were sent, could you have chosen this? A skill the
model is never told about is a skill that does not exist.
