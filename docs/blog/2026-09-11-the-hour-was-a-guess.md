# The hour was a guess

A message taken from the queue and not finished comes back after an hour. We
wrote that down in September, borrowed it from SQS, and called it a visibility
timeout. It is the line that makes the whole directory safe: a consumer can die
at any point and the question it took gets asked again.

The number came from nowhere. The decision record says so, in as many words: a
guess at a good default. Nobody argued with it, because an hour is obviously
longer than an answer takes.

An hour is obviously longer than an answer takes right up until it is not. A
coding agent asked to find why a deploy failed will read logs, run a test, read
more logs. Four minutes is normal. Forty is not strange. And the failure, when
it comes, is not the one you would design against. Nothing crashes. The message
is taken, the agent is working, the hour passes, and the sweep — doing exactly
its job, protecting exactly the case it was written for — puts the message back
in `new/`. The next consumer picks it up and starts answering a question that is
already being answered. Two agents, one question, two replies, and the second
one arrives first.

What makes this worth writing down is that the mechanism was not wrong. Every
part of it did what it was supposed to. The bug was in a unit: we had written a
timeout in seconds when the thing we meant was not a duration at all.

## What we meant

We never wanted to know how long an answer takes. We wanted to know whether
anyone is still working on it. Those are different questions, and only one of
them has an answer you can write down in advance.

So the consumer says so. While a handler runs, something touches the queue
file every few minutes. The sweep still looks at the timestamp and still
reclaims anything older than an hour — the code barely changed — but the
timestamp now means "last sign of life" instead of "when this was taken". A
ninety-minute answer is not interrupted. A consumer whose process was killed
still loses its claim, on the same schedule as before.

The hour stopped being a guess without becoming a better guess. It became a
number that does not have to be right, which is the only kind of number you can
safely leave in a config file for a year.

`ChangeMessageVisibility` is the SQS call that does this, and we had copied the
timeout without copying the renewal. Distributed systems have known this since
before we started: the lease, not the deadline. We had half of it.

## The other thing an hour protects against

Once the lease was in, a second failure got easier to see, because the first one
had been hiding it.

Some messages do not fail transiently. A payload the handler cannot parse, a
question that trips a bug, an attachment that makes the model time out — these
fail the same way every time. Under the old rule such a message was taken,
failed, returned after an hour, taken, failed, returned. Forever. Nobody
notices, because each individual hour looks like a retry, and retries are what
the directory promises.

The visibility timeout is a loop with no exit condition. It was written to
protect against a dead consumer and it works perfectly for that. Against a
message that kills consumers, it is a scheduler for killing consumers.

So we count. Every handout is recorded, in a file rather than in memory,
because the point of counting is to survive the crash that caused the retry — a
count in memory resets exactly when a message is about to be handed out for the
fourth time. On the fourth, the message is completed with a line in the log
saying we gave up. It is not answered and not silently dropped: it is finished,
on purpose, with a record of why.

Three is also a guess. But it is a guess about how many transient failures in a
row are plausible, and being wrong about that costs one unanswered question,
once. Being wrong about the old guess cost two agents answering one question
every hour until someone looked.

## Why this was the week for it

The directory had a shape and no users. The tool wrote messages into files; the
decision record said, deliberately, that deciding what to do with them belongs
to whatever consumes the directory. Then for a year nothing consumed it except
a shell loop.

This week the Agent started consuming it, and that is what made the hour matter.
A shell command answers in milliseconds and the guess was never tested. An agent
answers in minutes, sometimes tens of minutes, and it tests the guess on the
first interesting question somebody asks. The abstraction had been correct and
unexercised, which reads exactly like correct.

The rest of the week's work was ordinary — a rename, a loop, a config section —
and none of it is what we will remember. The renewal is. A timeout you have to
get right is a bug with a long fuse, and the fix is almost never a better
number.
