---
title: Half the messages went to someone else
date: 2026-10-26
description: A Lark listener looked healthy while another client on the same app took half its events, and the recovery meant to fill the gap had failed every minute for weeks.
---

Four direct messages went to the bot in a row. Two arrived. `co lark listen`
said `listening`, the socket was established, the log was alive, and nothing in
it said anything was wrong. People's messages went unanswered for hours, and
from the outside it looked like a listener that had died.

It had not died. Lark pushes each event to exactly one of the long connections
open for an app, and somewhere a second client was connected as the same bot.
That client received the other half. Our process could not see it, so it
reported healthy, which was true about its own socket and false about the bot.

History recovery exists for exactly this: read back what the socket missed.
It had never once finished. A reply in a group carries a `root_id`, which is a
message id (`om_…`), and the inbox stored it as the thread. Recovery then asked
Lark for the thread `om_…`, Lark answered `230001 invalid container_id`, and
one bad conversation aborted the whole run. The worker waited sixty seconds and
asked again. The log held about 23,000 copies of that line, and each one was an
API call against a monthly quota.

So the fix had three parts. Only a real thread id (`omt_…`) is read as a
thread. A conversation Lark rejects is logged once and skipped, and the rest of
the run goes on. And the sixty-second retry is gone. Our first idea was the
opposite: reconcile every few minutes, so a split would heal on its own. Aaron
said no, because Lark calls are a quota and the listener should stay
push-driven. Recovery still runs at start and after a reconnect, and a run is
now capped: at most 40 calls, two pages per conversation, newest first. A
permanent error costs one line until the next reconnect.

The split itself is now visible. When a recovery run finds a message addressed
to the bot that was sent while this listener was connected, outside any
reconnect gap, the socket should have delivered it, and the likeliest reason it
did not is another client. The log says that in those words, and
`co lark check` prints it.

While comparing the listener against WhatsApp's, we found a quieter gap.
WhatsApp records reactions, a bot being added to a group, and group changes as
inbox records with their own kind. Lark dropped every one of them, or answered
`processor not found` and got the event retried. They now arrive as
`reaction`, `recall`, `joined` and `group-info`. Files and images already came
through with their resource keys, and a test now pushes them through the real
SDK dispatcher to keep it that way.

Before the change, the regression tests failed on main the way the log did:
`om_root` queried as a thread, `Lark error 230001` raised out of `reconcile()`,
`retrying in 60 seconds`, 10,060 calls in one run against a fake that always
had more pages, and `processor not found` for a recall and a bot-added event.
After the change they pass, along with 739 inbox, Lark, Feishu and WhatsApp
tests. We did not connect to the real app. The client sharing its app_id is
still out there, and it is the next thing to find.
