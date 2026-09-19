# The way out was behind the lock

The browser daemon pins its engine when it starts. Every request carries the
engine the client resolved, and a mismatch was refused:

```
browser daemon is pinned to engine=onion; this request asked for engine=auto.
Close it with `co browser close`, then retry.
```

Read that carefully, because it is a closed loop.

A bare `co browser <verb>` resolves to `engine=auto`. So does
`co browser close`. If your daemon is pinned to the paid engine, the command
the message tells you to run is refused by the guard that printed the message.
Follow the instruction literally and you do it forever.

The escape existed — `co browser --engine onion close` — and nothing anywhere
named it. An agent working a task on an Airbnb host dashboard spent the end of
its session discovering that by hand, after the browser had gone and `tab ls`,
`status` and `close` were all refused with the same paragraph.

## Three separate mistakes wearing one costume

It is tempting to call this a bad error message. It is three things.

**The guard was reading `auto` wrong.** `auto` means *no preference*. The
daemon treated it as a preference that conflicts. That single misreading is why
every bare command against a warm paid daemon failed, and it had already been
filed separately as its own issue before this one existed.

**The guard was gating verbs that do not use an engine.** `tab ls` lists a
registry. `status` reads state. `close` tears the whole thing down. None of
them care which browser is running, and one of them is the documented way out.
Putting `close` behind the lock is what turned "annoying" into "unrecoverable".

**The remedy was untrue.** Not vague, not unhelpful — false. It named a command
that could not work.

## What `auto` should mean

The rule now: only a **named** engine that differs is a conflict. Ask for
`--engine system` on a paid daemon and you get refused, because you asked for
something specific and it is not what is running. Send a bare command and it
rides whatever is up.

There is exactly one exception, and it is money.

A running paid session is consent that was already given — somebody typed
`--engine wtf` to start it, and another tab inside it charges nothing further.
But once that session has ended, serving `auto` would quietly open a *new*
billing interval on behalf of a command that never asked to spend anything. So
that one case still asks:

```
browser daemon is pinned to engine=wtf and its paid session is no longer open.
Starting it again bills, so a command with no engine of its own has to say:
```

Consent is the live session, not the flag someone typed an hour ago.

`tab open` stays guarded for the same reason. It reads like a bookkeeping verb
and is not: it allocates a page, and on a paid pin that spends.

## The test that earned its keep in five minutes

The messages now name only commands this daemon would accept in this state, and
they use the name a person types — `wtf`, the product's name — rather than
`onion`, which is only how the wire spells it.

That is easy to assert badly. A test that checks for the substring `close` tells
you a word is present, not that the advice is true. So the property is tested
directly: take every `co browser ...` line a refusal prints, dispatch each one
back at the same daemon, and require that none of them is refused.

It failed on the first run. My draft of the paid-relaunch message offered:

```
Free, and your logins are still there:
  co browser --engine system <verb> ...
```

which a `wtf`-pinned daemon refuses as a named conflict. The exact bug being
fixed, reintroduced in the fix for it, caught before review by a test written
because of it. The real remedy is `close` first — the pin is immutable while
the daemon lives — so that is what the message says now.

## The cheapest part was the one nobody asked for first

Filed under "lower priority" in the report: nothing said which engine was about
to bill.

The session that hit all of this ran an authenticated host dashboard on the paid
anti-detection browser for forty minutes, lost the session twice, and then —
after being forced onto the free engine by the failure — finished the identical
work with the logins still intact. The paid engine contributed cost and
instability and no benefit, and there was no moment where anything said so.

So a session-starting verb on the paid engine now prints one line before the
command is even sent:

```
⏱  The WTF Browser bills for the session this starts.
   A site you are already logged into rarely needs it:  co browser --engine system <verb>
```

Before the spend, not in the receipt.

## Not fixed, and said out loud

When the paid browser exits on its own, the tab registry goes with it, and the
next command fails on a missing tab — which reads as a second, unrelated fault.
The error now names the way back. The registry surviving a crash, and
reconnecting at all, is a design change about what a tab entry means with no
page behind it, and for the paid engine a reconnect is a new billing interval,
which drags it back onto the consent question above. That is filed, not rushed
into a beta.

## The rule

An error message is a promise. Print a command and you have asserted it works.
If you cannot test that assertion, you are not writing a remedy — you are
writing a plausible sentence, and a plausible wrong sentence costs more than
silence, because the reader trusts it enough to repeat it.
