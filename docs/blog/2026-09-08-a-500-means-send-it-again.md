# A 500 Means "Send It Again"

We reviewed the Feishu listener before its first live run, and the first
thing we did was give it wrong credentials on purpose. `co lark listen` with
a made-up app id printed forty lines of traceback ending in
`ClientException: 1000040346: app_id is invalid`. The sentence at the bottom
was the whole diagnosis. The thirty-nine lines above it were Typer, the SDK,
and our own call stack, none of which the operator can act on. Worse, the
tool's own log already had the answer eight seconds earlier: `bot info
failed: Feishu refused the credentials: 10003 invalid param`. The listener
had asked Feishu who it was, been told no, written that down, and then
dialled the WebSocket with the same pair anyway.

That second part is the one worth writing down. The official SDK reconnects
on its own, which is exactly what you want when the network blinks. It is
exactly what you do not want when the credentials are wrong, because the
reconnect loop turns one clear refusal into a `connect failed` line every two
minutes, forever, and a person reading the log at hour three sees a network
problem. The fix is to tell the two apart at the one place we can. When the
bot-info call comes back with a Feishu error code, Feishu answered and said
no; there is nothing to retry, so `listen` stops, prints the sentence, and
exits 1. When the call gets no answer at all, a DNS failure or a proxy, the
long connection may well get through, so it proceeds and lets the SDK do its
job. Same exception handler, two `except` clauses, and the difference between
them is whether the platform spoke.

The second finding came from reading the SDK rather than running it. The
event handler we register is called from inside the SDK's frame loop, and
that loop wraps the call in a `try`. If the handler raises, the SDK logs the
error and answers Feishu with HTTP 500. Feishu's documentation says what a
500 means: not delivered, send it again, fifteen seconds later, then five
minutes, then an hour, then six. So a message the adapter could not parse,
say a field the SDK model spells differently from what we expected, would
not be lost. It would come back for the rest of the day, each time raising
the same exception, each time producing the same 500. Our handler now
catches its own parse failure, writes one line, `event not understood
(AttributeError: ...); skipped`, and returns normally. Feishu sees a 200 and
moves on. The one exception we leave uncaught is the file write itself: on a
full disk, "not delivered, send it again" is the truth, and the redelivery is
the thing that saves the message.

Neither of these is a bug the unit tests could have found, because both live
in the seam between our code and the SDK's behaviour on failure, and the
tests fake the SDK. They are the kind of thing a review finds by asking "what
does the other side do when we raise" and going to look. The three
regression tests that now pin them fake the SDK too, but they fake the part
that matters: a `start()` that delivers a broken event before a good one, a
token endpoint that says 10003, a provider whose `run` raises. Each failed
on the unpatched code for the reason the defect predicts, which is the only
evidence a regression test can offer.

The smallest change in the review is the one people will notice. Every error
message said "Feishu", including the ones a `co lark` user sees. Lark is
Feishu outside China, same API, different console at a different address; a
person told "Feishu refused the credentials" goes to open.feishu.cn to fix
it, where their application does not exist. The adapter now knows which
brand it is talking to and says so.

## The second pass

A second, adversarial review ran over the same diff with the findings
above already in, and it found the thing the first pass had made worse.
The listener logs a message before it queues it, on purpose, so that a crash
between the two writes leaves a message the log knows about. The blog post
for the original PR says this case is "recoverable by reading the log". It
was not, in practice: the redelivery Feishu sends after the crash hit the
duplicate check, which looked only at the log, and was dropped with
`duplicate om_x dropped`. Log-first ordering had turned the platform's own
recovery into a false positive. The check now asks where the message is,
not whether it has been seen: an id in the log is a duplicate only while a
file for it sits in `new/` or `cur/` or an answer to it sits in the outbox.
In none of those places, the earlier attempt died mid-write and the
redelivery is the recovery; it is queued and the log is left alone.

The lock had the same shape of problem. It was a pid in a file created with
`O_EXCL`, and `O_EXCL` creates the file empty an instant before the pid is
written. A second `receive` starting in that instant read an empty file,
concluded the pid was dead, unlinked the winner's lock and started its own
listener: two long connections, every message written twice. And after a
reboot the pid in the file belongs to whatever the OS handed that number to
next, which `os.kill(pid, 0)` reports as alive forever. The repository
already had the right primitive in the browser daemon, an `flock` the kernel
releases when the holder dies, SIGKILL and reboot included. The pid is still
written into the file, for `check` to print, but nothing decides anything by
it any more.

The rest of the second pass was the kind of list a first live day produces:
`serve` consumed a message whenever the command failed, so a 529 from the
model turned into a question nobody answered; `.DS_Store` in `new/`, which
Finder writes when you open the directory the docs tell you to open,
crashed every consumer; `@_user_1` is a prefix of `@_user_10`, so a message
tagging ten people lost the tenth; `reply --again` with the same words
reused the same Feishu reply key and was silently swallowed while the CLI
printed a message id. Each is a test that failed on the old code first.

The live run against a real group is still owed, and the tool stays a
preview until it has happened. What the two reviews bought is that the
first person to run it will get a sentence when it fails, not a stack; that
the first malformed event will cost one log line, not a day of retries; and
that the first crash between two writes will be recovered by the redelivery
the design always said would recover it.
