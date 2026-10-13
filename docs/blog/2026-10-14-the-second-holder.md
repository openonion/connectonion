# The second holder

*2026-10-14*

We pasted the same handoff line into two Codex windows on one machine, as if a
mail had been forwarded to a colleague. The first one finished in under four
minutes. The second accepted, asked a question, and then sat on "Waiting for
news…" for as long as we watched.

Nothing was wrong on the sender's side: it saw a second acceptance, counted it as
"ignored", and moved on. The second agent was never told. Our rule said "after
about 10 minutes, carry on and say what you assumed", but the agent was blocked
inside the command that waits, so it could not apply the rule.

So the rule moved into the command. `status --wait` returns after ten minutes
with the carry-on line, and the sender's agent tells each other holder, once,
that the handoff is already someone's.

The same evening a handoff reached a colleague who was named 61 times in it.
Masking had removed every address and phone number, but not what the
conversation said about him. The preview now says how often the recipient is
named, and `--mentions` shows each place before you send.
