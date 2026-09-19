---
title: Thirty-four events we were not listening to
date: 2026-09-18
---

# Thirty-four events we were not listening to

A WhatsApp session in production stopped working. The symptom, from the
operator's side:

```
$ co whatsapp send "1203…@g.us" "test"
the store doesn't contain a device JID

$ co whatsapp check ; echo exit=$?
✓ whatsapp reachable · listener pid 97492 · 0 unread
exit=0

$ co whatsapp listen
listening · /Users/…/.co/inbox/whatsapp
```

Sending is broken. The diagnostic is green. The listener reports normally and
receives nothing, forever.

## Counting what we subscribed to

neonize exposes 37 events. We had handlers for three: `ConnectedEv`,
`MessageEv`, `PairStatusEv`.

Among the thirty-four we ignored:

- `LoggedOutEv` — the phone unlinked this device
- `StreamReplacedEv` — another client took the session over
- `TemporaryBanEv` — WhatsApp banned the number for a while
- `DisconnectedEv`, `KeepAliveTimeoutEv`, `ConnectFailureEv`

Every one of those was being delivered to our process and dropped on the floor.

The first three are *terminal*: no amount of waiting fixes them. And our
listener, on receiving one, kept its socket open, kept printing nothing, and
kept not receiving messages — because from the inside, a connection that will
never deliver again looks exactly like a quiet afternoon.

## What I measured before designing anything

The report said `listen` starts and silently receives nothing. My instinct was
that `listen` should refuse to start on a logged-out session. That instinct was
wrong, and running it is what showed me:

```
$ CO_INBOX_HOME=… co whatsapp listen
listening · …
████ ▄▄▄▄▄ █▀▀█▀█ ▀▄██  █▄█▄█ ▄▄█▀ ▀█ ▀▀ ▄▀▀▄  █▄▀▀▀█ █  █ ▄▄▄▄▄ ████
…
```

It shows a QR. Starting fresh on a logged-out session works correctly — it
offers to re-link. Had I built the refusal I was planning, I would have broken
the only way to recover and fixed nothing.

The real failure is narrower and could only have been found by asking what the
reporter's process was *doing at the time*: it was **already running** when the
phone unlinked it. A listener that starts can show a QR. A listener that is
already connected cannot go back and show one.

## Stopping is a feature

The fix is that three events now end the listener with a specific exception and
exit 3:

```
logged out by the phone (reason 401). This device was unlinked under
Settings > Linked devices. Next: co whatsapp listen — scan the QR again
```

Exit 3 is this CLI's code for "a credential is missing" — which is exactly the
right category. Something needs a human before any restart helps. A supervisor
that retries on 1 and gives up on 3 does the right thing without being taught
anything about WhatsApp.

The transient events become log lines instead. `DisconnectedEv` is not a
failure; the SDK reconnects. But it is the thing you need to see afterwards when
somebody asks whether a message could have been missed, so silence there is its
own small bug.

The distinction — terminal versus transient — is the entire design. Treating all
disconnections as fatal would take the listener down every time a laptop's wifi
blinked. Treating none of them as fatal is what we were doing.

## The message that named a data structure

```
the store doesn't contain a device JID
```

That is whatsmeow's sentence and it is completely accurate. It is also about a
store and a JID, when the thing that happened is *your phone unlinked this
device*. One is a fact about our internals; the other is a fact about the user's
week.

Only that one error is translated. Anything else keeps its own words — a message
someone can paste into a search beats a fix I guessed at, which is a lesson from
three separate bugs this week.

## And the one the file cannot answer

`check` used to say "a QR code was shown but no phone confirmed it". For this
operator that is false: theirs had been linked and working for days.

whatsmeow deletes `device`, `identity_keys` and `sessions` together on logout,
so a pairing that never completed and a device that was unlinked leave
byte-identical files. There is no way to tell them apart from disk, and picking
one sends half the people who read it looking for something that did not happen.

So it says both:

> No linked device in …/session.db — either the QR was never scanned, or this
> device was logged out from the phone.

Saying "I don't know which of these two it is" is more useful than confidently
saying the wrong one, and it costs eleven words.

## The rule underneath

When you subscribe to a platform's events, the ones you do not handle are a
decision, not an absence. We had decided, without noticing, that being logged
out was not worth mentioning.

A good way to find that class of bug: list everything the SDK can tell you, and
for each one you ignore, finish the sentence *"if this happens, the operator
will see…"*. Thirty-four times, our answer was "nothing at all".
