# The Long Tail of a Default

We changed the default model three times. The constant, once. The rumor took
three passes.

Pass one was #1021: `DEFAULT_MODEL = "co/gemini-3.7-flash"`, one constant,
imported everywhere the code needs an answer to "what model do I use when the
user says nothing." That PR even told this story — fifty-nine hand-typed
copies of the old default, collapsed into one name. We shipped it and felt
done.

Pass two was the stable line. The same change, ported, released. Done again.

Then someone read the docs.

`docs/concepts/models.md` recommended `gemini-2.5-pro` as the flagship — twice
in a row, on consecutive lines, because at some point a copy-paste stuttered
and nobody reads a model catalog closely enough to notice. The transcribe
guide showed `gemini-3.5-flash`. The browser-agent example — the one we point
new users at — was pinned to `co/gemini-3.5-flash` in its `Agent(...)` call.
The subagent registry's code said 3.7 while its own docstring, six lines up,
still said the explore agent runs on 2.5-flash. The docstring wasn't lying
when it was written. It just never heard the news.

My favorite one: `.github/scripts/check_blog_story.py`. That's the CI gate
that judges whether a dev-blog post reads like a story — the gate this very
post has to pass. It calls `llm_do` with an explicit model, because a gate
should be pinned, not drift with the default. Reasonable. Except the pin was
`co/gemini-2.5-flash`. For two releases, every post announcing that 3.7 is
the new default was quality-checked by a 2.5 model. The gatekeeper for the
news was the last one to receive it.

So pass three was a sweep: grep for every 2.5-, 3.5-, 3.6-era name outside
the tests, and read each hit. Not replace each hit — read it. Because about
a third of them turned out to be true.

The pricing table's row for `gemini-2.5-flash` at $0.15/$0.60 is not stale;
it's what Google charges for a model they still sell. The free-models list
keeps `co/gemini-3.6-flash` on purpose — it's the rollback if 3.7 misbehaves,
and a rollback you deleted from the docs is a rollback nobody can find. The
skill file that says "measured on 8 tips with co/gemini-2.5-flash, 2026-08"
records a measurement; rewriting the model name would forge the lab notebook.
And yesterday's blog post about the 3.6-to-3.7 switch has to keep saying 3.6,
because that's what it was. A sweep that can't tell an example from a fact
doesn't clean the docs — it launders them.

Here's the lesson I keep relearning. A default is not a constant. The
constant is the smallest part of it. A default is a rumor: every docstring
that mentions it, every example that hardcodes it because autocomplete
offered it, every scaffold comment, every CI script whose author pinned
"whatever the default was that day." The constant updates atomically. The
rumor updates the way rumors do — one correction at a time, and only where
someone bothers to go look.

The fix for the constant was #1021. The fix for the rumor is this PR, three
hundred-odd mentions later. And the honest ending is that there is no fix,
only a lower steady state: the next default change will leave a tail too.
The best we did for future-us is make the tail greppable — old model names
now appear only where they're facts, so the next sweep can read the diff of
truth instead of the whole repo.
