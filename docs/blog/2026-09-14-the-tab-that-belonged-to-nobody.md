# The tab that belonged to nobody

"Some pages, when you open them, also open a third page in a new tab. If we
can't switch tabs, we can't do anything in that one."

That is the whole bug report, and it is a good one, because it names a situation
rather than a feature. The situation is common: a "view invoice" button, a
payment popup, an OAuth consent window, any `<a target="_blank">`. The work moves
to a page, and the agent stays behind.

## Why it was invisible rather than broken

`co browser tab ls` was working perfectly. It listed every tab — every tab *we*
had registered.

```
Tabs (1):
   [work] file:///tmp/opener.html  who=tabswitch  purpose='tab switch'
```

One tab. The browser had two pages open. The second one was right there, loaded,
titled, sitting in `context.pages`, and nothing in the product could name it.

Our tab board is a board of *sessions*: one agent, one task, one page it drives.
That model earns its keep — it is what stops two agents silently interleaving on
one page. But it has a blind spot exactly the size of a page that arrived without
a session, and a site opening its own tab is precisely that.

So every `-t work <verb>` kept running on the opener. Correctly. Forever.

## The verb that was already deleted

1.8 removed `use` and `switch` with a good reason:

> use/switch removed — target a tab per command instead: `co browser -t <tab> <verb>`

A server-side cursor for "which session does a bare command mean" is a race
between two terminals, and per-command targeting is strictly better.

But "switch" names two different things. The removed one chose which *session* a
command belonged to. The missing one chooses which *page* a session drives. When
someone hit the wall this report describes and typed `switch`, they got a message
about the first, which is not what they were asking for — a correct answer to a
question nobody asked.

That message now answers both.

## Two lines that would have been quietly wrong

**The sentinel.** My first version of "who is driving this page?" returned `None`
for "nobody".

`None` is already the main tab's session key.

So the shared `main` tab would have listed as *unclaimed*, and `switch_page`
would have handed it to whichever second agent asked — the exact contention this
subsystem exists to prevent, introduced by the feature meant to extend it. The
fix is a sentinel object, and the reason is in the code, because "why isn't this
just None" is a question the next person will have.

**The discoverability.** `list_pages` is useless if you do not know it exists,
and the person who needs it is, by definition, looking at the tab board and not
finding their tab. So the board counts what it cannot show:

```
1 open page no session is driving — the site opened it itself.
  co browser list_pages
```

A feature nobody can find is a feature nobody has.

## The probe was wrong before the code was

The unit tests passed against fakes. That is not the claim, so I drove a real
browser: load a page that calls `window.open()`, then list the pages.

One page. The popup never appeared.

For about a minute that looked like the feature not working. It was the test not
working — Chrome blocks popups that no user gesture requested, and `data:` URLs
are restricted besides. My scenario was one a browser is designed to refuse.

The report had actually described the right one all along: *opening a page* opens
another. A click on `<a target="_blank">` is a user gesture. With that:

```
Pages (2):
  *0: file:///tmp/opener.html  [work]  'Opener'
   1: file:///tmp/popup.html   unclaimed — no session is driving it  'The Popup'

Now driving page 1: file:///tmp/popup.html
REACHED THE NEW TAB: True
```

The lesson is not "test with a real browser" — I did. It is that a negative
result from an instrument you just built tells you about the instrument first.
The fastest way to be wrong here would have been to trust the first run and start
debugging code that was fine.

## What this does not do

It does not watch for new pages, notify anyone, or switch automatically. A page
appearing is not a reason to go there — the agent decides. All this restores is
the ability to decide at all.

And a page another session drives is refused by name, same as tabs. Extending
what agents can reach is not a reason to weaken what keeps them apart.
