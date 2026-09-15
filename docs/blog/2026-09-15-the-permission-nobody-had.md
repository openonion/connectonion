---
title: The permission nobody had
date: 2026-09-15
---

# The permission nobody had

1.8.5 is out. The headline is that a Feishu or Lark bot is now a directory of
files — nine verbs, an atomic take, and a message sent while you were
disconnected read back on reconnect and queued exactly once.

That last clause held the release for a week. This is what was actually wrong,
because it was not what any of us thought.

## The gate

On 8 September a live test cut the listener's connection for 135 seconds and
posted a message into the gap. The listener reconnected. The message never
arrived — confirmed still sitting on Lark's side, absent from the inbox 175
seconds later.

So we wrote `HistoryRecovery`: on reconnect, read back the conversation's own
history, deduplicate by the provider's message id, queue anything missing. Eleven
unit tests. Careful about checkpoints — advance only after every page succeeds,
so a partial failure cannot skip past a message it never read.

Then it sat there for a week, because a repeat of the live test was blocked on
something nobody had written down clearly.

## What the repeat found

It failed the same way. And this time the log said why:

```
history recovery incomplete; checkpoint retained: Lark error 230027:
Lack of necessary permissions, ext=need scope: im:message.group_msg
```

The bot could not read the history it had been written to read. Not once, not
since it was created. Every recovery pass since the feature shipped had failed
at the first API call, held its checkpoint, written an error file, and retried
sixty seconds later — correctly, loudly, and to nobody, because nothing was
watching the log of a feature that had never worked.

Two setup routes lead to a bot. `co auth lark` creates one and asks for no scopes
at all. The manual instructions in our own documentation list three scopes, and
`im:message.group_msg` is not among them. **Neither route has ever produced a bot
that could run recovery.** The safety net was not failing under load; it had
never been deployed.

## The part I got wrong twice

The fix is a link. Lark's platform takes a URL that carries a scope request and
shows the owner a confirm page — one click, no Developer Console visit.

My first attempt built that URL and got three details wrong at once: the path
(`/page/cli`, which is the registration flow, instead of `/page/launcher`), the
identifier (`user_code` instead of `clientID`), and the payload shape (one scope
array instead of both, where the spec reads a missing side as empty).

The page answered **"App updated."** Nothing had been granted.

I only found the right shape by reading `lark-cli`, which is open source and
solves this exact problem in `cmd/event/console_url.go`, with a comment that is
the whole contract:

> The bot-specific scan-to-enable link adds the scopes to the app manifest,
> after which the tenant token carries them.

Aaron told me to go read it three times before I did. The first two times I went
back to probing the platform instead — running more experiments inside a frame
whose one wrong assumption sat outside it. Every probe was sound. Every probe was
downstream of the URL I never questioned.

A working implementation of the same problem is a statement about what is
possible. It was installed on the machine the entire time.

## Then it passed

Same tenant. Listener killed at 05:12:24, a message posted at 05:12:29, a
ninety-second gap, listener back at 05:14:04:

```
05:14:05Z  history recovery complete: 1 new message(s)
```

One copy in the queue. No duplicates across the day's four messages. And no
`received` line for it — that line is what the WebSocket path writes, so recovery
is what delivered it. Every earlier gap that week had been quietly covered by
platform redelivery. This one was not, and the net caught it.

First time that path had ever succeeded against a live connection.

## What the release actually changed

The scope is now asked for at registration, so a new bot arrives able to do the
work. A missing one prints the link that grants it, with a plain warning that it
is sensitive — it lets the app read every message in the groups it is in. And the
documentation that told people to treat a disconnection as possible message loss
is gone, because that stopped being true.

## The shape of it

Three times in one week the same failure: a thing that looked like it worked,
reporting success, while doing nothing.

Recovery failed loudly for a week and nobody heard it. `co gcalendar` created
events with attendees and invited none of them — and printed `Event created`,
which read identically whether three people were invited or nobody was, so the
silent failure was indistinguishable from success until a client's guest
mentioned it. The scope link said "App updated" while granting nothing.

None of those were crashes. All three were confident output describing something
that had not happened.

So a good part of 1.8.5 is unglamorous: making the CLI say what it actually did.
`Invitations sent: a@example.com, b@example.com` — the line's absence is now
equally the signal. A refusal naming one next step instead of two. A mistyped
command ending at something you can run rather than at `--help`. A confirmed
meeting time echoed in the zone you typed rather than converted, because
`06:30 AM` for a 4:30pm meeting is right and useless.

A tool that fails loudly costs you an afternoon. A tool that succeeds quietly
costs you a meeting, and you find out from the person who was not invited.
