# Outlook as an inbox: two of twenty-six

*2026-10-17*

#1733 came from a founder about to travel for four weeks who wanted an agent to
answer the emails from six student teams. There was no Outlook channel, so the
first try was a polling script, and it broke three ways in one evening: a
last-N listing missed two teams buried under notifications, `$search` kept
timing out, and every restart needed a seen-file.

I rebuilt that in a test mailbox (imported through Graph, since the account
can't get outside mail): 24 student emails under 30 notifications, plus 2 in
Junk. Listing the last 10 found 2 of the 26.

The provider uses Graph's delta query instead. A delta link remembers where you
stopped reading a folder, and following it gives you everything since, page by
page. `co outlook listen` keeps one per folder, Inbox and Junk by default.

The one real decision was when to save that link. Saving after each page seemed
fine until I thought about a crash halfway through a round: the rest of that
round would never be read. So it only saves after a full round, and if it
crashes the round just runs again (the inbox ignores what it already has).

On the test mailbox the first round got all 26 student emails and none of the
notifications, the next round got nothing, and after a restart it only picked
up the 3 new ones.

Still missing: push notifications instead of polling, and the 410 case (Graph
dropping the sync state) has only been tested in unit tests. The Graph calls go
through the Outlook tool's own client, so the listener shares its token refresh
and retries, and needs nothing new installed.

```bash
co auth microsoft
CO_OUTLOOK_FROM='*@student.unsw.edu.au' co outlook listen
```
