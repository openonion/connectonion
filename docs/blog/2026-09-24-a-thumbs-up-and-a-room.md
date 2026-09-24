# A thumbs-up and a room

Four people set up a meeting in a client's WhatsApp group in about ten
messages — "How abt 4pm", "Ok ok bring Zekai tgt", "Looking forward to see u
guys". A person in that room would have dropped a 👍 on two of them and said
nothing. The agent could not. Its reactions only ever landed on messages it was
about to answer, as read receipts, so its choices were silence or a whole
message, and a whole message was louder than the moment deserved.

The plumbing for a reaction already existed; the bot reacts to its own queue
every day. What was missing was a way to point it at any message — anyone's,
from any time. `co whatsapp react <id> 👍` does that, and `""` takes it back.

The one trap was ours. WhatsApp addresses a reaction by who sent the message
being reacted to. The code filled that in with the chat when it had no sender,
which is right for somebody else's message in a direct chat and wrong for our
own message in a group, where the author is us. Our own messages now say so
explicitly, and the listener uses the account's own id for them.

The same week a client called and someone had to set up a room — the client
plus two or three of us. The answer was "a human has to create the group on a
phone, then add me". `co whatsapp group create` and `group add` fix that, but
the interesting part is the output, not the command. WhatsApp reports a group
as created while quietly leaving out a number whose privacy settings forbid
being added. An agent that trusted the overall success would tell the team the
client was in a group the client had never seen.

So every number gets its own line. A number with no WhatsApp account is never
sent at all and says so; a number that refused says it can only be invited, and
the group's invite link comes back with it; and a number WhatsApp's answer
simply did not mention is reported as *not confirmed*. The first version of
that last case said "added", on the reasoning that no error meant success. That
is exactly the inference this command exists to stop anyone making, so it went.

Exit 1 means at least one person is not in. The group exists either way; what
the exit code answers is whether the room is ready.
