---
description: Before releasing automatic answers that send a copy of the session, we ran the redaction on a real session and counted what survived. Forty-four handoff codes did.
tags: [Handoff, Security, Release]
---

# Forty-four keys in the copy

The new automatic answer sends the other agent a copy of the session the
handoff came from. Before it goes, a redaction pass removes anything shaped
like a credential: API keys, tokens, invite codes, and every value in the
sender's keys file. The tests for it passed. Before releasing, we ran it on a
real session, the three-day one this feature was built in, and counted what
it removed and what it left.

It removed sixteen things: five API-key-shaped strings, three invite codes,
three secret assignments, a token, and a value from the keys file. Then we
searched what was left for things the patterns did not know about, and found
forty-four handoff codes.

A handoff code is not a password in the usual sense, which is why the patterns
missed it. It is the string a person pastes to take over one handoff, and it is
also the secret that proves you are the one who took it: whoever has it can
accept that handoff or ask about it. A session that sends and tests handoffs
is full of them, for handoffs to other people. Sending the copy to one
recipient would have handed them the keys to everyone else's.

The fix was one line, a pattern for the code. The lesson is in how we found
it. A redaction is tested against the secrets you thought of, and every test
passes by construction. The useful test runs it on real data and reads what is
left, because what you did not think of is exactly what survives.
