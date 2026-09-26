# The number on the screen

The audit replayed an ordinary morning against a fake mailbox. The afternoon
before, an agent had listed an Outlook inbox; the board minutes from the CEO
were #1. Overnight a customer wrote in with an invoice question, and
the agent, doing the careful thing, listed the inbox again — this time with
`--json`, because it wanted to parse the result instead of reading a table. The
customer's email was at the top of the array. So it ran:

```
co outlook reply 1 "Thanks, invoice attached"
```

The reply went to the CEO.

Nothing crashed and nothing looked wrong. `co outlook` remembered "the last
listing" in one file, `~/.co/outlook_last_inbox.json`, and the command that
looked like a listing did not write it: `--json` printed the array and left
yesterday's numbering in place. An empty search did the same, and so did an
empty unread listing — each one returned early, the way you would write it if
"nothing to show" meant "nothing to change". The file had no expiry and no
idea which account it belonged to. Row 1 meant row 1 of whatever table had
last been saved, and the only table the agent had looked at was a different
one.

We had already been here. Gmail and Drive went through the same bug earlier in
the year, and the fix there was not a smarter cache but a different contract:
every listing that shows numbers writes its own small, immutable file and
prints its token, `Listing: 3f9a…`. A number is only a number *together with*
that token. The file is bound to the account, dies after 15 minutes, and no
later listing — full, empty or JSON — can change what an older token's rows
point at. A bare number is refused with a message that says to pass
`--listing`. Full message IDs never needed any of it.

Outlook now uses the same module. `reply 1` without a token fails before any
mail is sent. `reply 1 --listing <token>` answers exactly the row the agent
saw, and a token from a different mailbox or from twenty minutes ago is turned
away. `--json` freezes nothing, because its rows carry IDs, not numbers.

The lesson we keep relearning is that a short reference is a claim about
*which screen* the user is looking at, and a single "last" file cannot make
that claim — any command that forgets to update it quietly moves the
reference somewhere else. Tie the number to the listing that printed it, and
the question "which list did you mean?" has only one answer. The test for it
replays the morning exactly: list, new mail, `--json`, `reply 1` — and checks
that nobody got an email.
