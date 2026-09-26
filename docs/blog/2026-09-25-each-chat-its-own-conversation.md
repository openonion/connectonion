# Client B asked what the bot knew

Picture the setup `co ai` was built for: one agent, a `host.yaml` that lists a
Feishu channel, and two client groups the bot has been invited into. Client A
writes first: "SECRET: our margin is 42%". A little later client B, in a
different group, writes "hi, what do you know?".

The code audit of 26 September ran exactly that, with a real `Agent` and a fake
model that wrote down everything it was sent. When it came time to answer
client B, the model was handed two user messages, not one:

```
['SECRET: our margin is 42%', 'hi, what do you know?']
```

And from then on the two chats were one: `sessions['clientA:'] is
sessions['clientB:']` was `True`. Whatever either client said, the other's
next answer was written with it in view.

## One missing line, and a test that agreed with it

The consumer kept a dict of sessions, one per conversation, and answered each
message with `agent.input(text, session=sessions.get(key))`. For a chat it had
never seen, that is `session=None`, and the comment above it explained the
choice: an empty session dict would start the turn without the system prompt,
so a new chat passes nothing and "starts fresh".

That is not what `Agent.input` does with nothing. No session means "carry on
with the one you already hold", which is how a script calls `input()` twice
and gets a conversation. The agent held the last chat's history, so the new
chat was appended to it, and the dict the consumer stored for B was the very
dict it had stored for A.

The unit tests passed the whole time, and that is the part worth keeping.
They used a `FakeAgent` whose `input(session=None)` started a new
conversation, because that is what the person who wrote the fake believed
`None` meant. The fake encoded the same misunderstanding as the code, so the
test could only ever agree with it. The fix to the test was bigger than the
fix to the code: the tests now drive the real `Agent` over a fake model, and
check what the model was sent, including two chats talking at once.

The fix to the code is to say "start over" out loud. A chat's first message
calls `agent.reset_conversation()` first, so it begins with the system prompt
and nothing else, and later messages pass the chat's own stored session, of
which `input()` takes a copy. The Host, which answers the same channels
through `input_handler`, did not have the bug: it builds a fresh `Agent` per
turn and keys the stored session by chat. It got the same real-agent test
anyway, so that stays true.

## The same audit found a quieter lie

Both consumers started a background listener and then stopped looking at it.
`co ai` ignored whether it started at all; the Host checked once, at startup.
A listener that was refused a token an hour in left both of them polling an
empty queue forever, while the console still said `answering feishu`. From
outside, a dead listener and a quiet group look exactly alike.

`co feishu receive` had already learned this the hard way and watched its
listener every second. That watch now lives in the inbox package, and `co ai`,
the Host and `consume` all use it. A listener that dies gets restarted. One
that exits 3, the listener's code for "a person has to act", gets its reason
printed once and that channel stops being served, because restarting a
revoked token only repeats the refusal. The web UI and the other channels
keep going.

## What it teaches

A fake is a claim about how the real thing behaves. When the claim is wrong
in the same direction as the code, every test agrees and nothing is tested.
Here the cheapest real thing, an `Agent` with a model that only records what
it was sent, was cheap enough to use from the start, and it would have caught
this on the first run.
