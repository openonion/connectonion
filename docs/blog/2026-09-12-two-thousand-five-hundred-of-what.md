# Two thousand five hundred of what

Three unattended LinkedIn rounds died on the same afternoon. Each one's first
timeout was a `wait` call, and from that moment every command against the
round's tab timed out at the client's 120-second ceiling — including the
`tab close` that would have released it. The 18:00 round spent fourteen
minutes and seven timeouts to post one comment out of forty-three extracted
posts.

Everything you would check said the browser was fine. `co browser status`
answered. Other tabs kept working. A second agent on the same browser saw no
problem at all. So the next round's health probe found nothing to restart, and
the diagnosis went first to a prompt regression and then to a duplicate daemon.
An hour, before anyone tried `wait` on its own.

The command was:

```bash
co browser -t <tab> wait 2500
```

`wait` takes seconds.

## The unit was guessable, and we guessed wrong for them

This is not a typo. Look at every other settle knob in the same tool:

```
click_element_near_selector(..., wait_ms=1000, ...)
upload_file_after_click_by_selector(..., timeout_ms=5000)
```

and the skill that teaches the workflow:

```
--require_anchor_text=true --wait_ms=2500 --verify_anchor_text_cleared=true
```

Milliseconds, milliseconds, milliseconds — and then one verb, spelled `wait`,
in seconds. An agent reading those files and writing `wait 2500` is not being
careless. It is being consistent with everything around it.

Two thousand five hundred seconds is forty-one minutes.

## What the mistake actually bought

Forty-one minutes of `page.wait_for_timeout` is not, by itself, interesting.
The interesting part is where those minutes were spent: inside the tab's
operation lock.

Same-tab commands are serialized on purpose. That is a contract with a test
holding it in place — one tab is one task, ordered, so two steps of the same
job cannot interleave on one page. It is the right design. It also means a
single argument could make the queue behind you forty-one minutes long, and
that the queue is invisible from outside: the daemon is not stuck, it is
working, on exactly the thing it was asked to do.

So the failure had no shape anyone could recognise. A wedged process looks
wedged. This looked healthy.

## The fix is a cap, and the cap is not about rationing

`wait` is now capped at sixty seconds, and refuses past it:

```
ValueError: wait takes seconds, not milliseconds: 2500 seconds is 42 minutes,
over the 60s limit.
  Did you mean `wait 2.5`?
  A wait holds the tab, so anything longer belongs in a condition, not a sleep:
  wait_for_element(<description>)  ·  wait_for_text(<text>)
```

The limit is not there to ration waiting. Nothing that needs more than a minute
of stillness should be a blocking sleep on a resource other agents may be
queued behind — that is what `wait_for_element` and `wait_for_text` are for,
and they return the moment the condition holds instead of burning the whole
budget every time.

Two details in the implementation are the whole point.

**The refusal happens before the lock is acquired.** A guard inside the
critical section would still have cost the round its tab. The check runs first,
touches nothing, and returns.

**The message names the value you meant.** `2500 / 1000 = 2.5`, and 2.5 is
under the cap, so the error says `Did you mean wait 2.5?`. An error that only
says no leaves the reader to work out the unit from the same files that misled
them in the first place.

## Both spellings, or it is not a limit

The verb exists twice: the async core the daemon runs, and the pre-asyncio
implementation still shipped as the oracle for the verb contract. Both got the
guard. A limit the two disagree about is not a limit — it is a limit plus a
way around it, and the way around it is the one nobody is testing.

## What we measured

The regression test was run against unguarded code first. Four of its six
assertions fail there, including the one that reproduces the damage through the
daemon: open a tab, send `wait 2500`, then send `status` to the same tab and
give it ten seconds. Unguarded, that test waits out the full sleep. Guarded, it
returns immediately.

Then the same command on a real paid browser session:

```
22:39:27  co browser -t w2 wait 2500
          ValueError: wait takes seconds, not milliseconds...
22:39:27  co browser -t w2 get_current_url
          https://example.com/
22:39:27
```

Same second, all three. Before this change, that first line held the tab until
23:20.

## The lesson that generalises

The unit was documented. `co browser help` printed `wait(seconds)` the whole
time. Documentation loses to consistency: when nine neighbouring parameters say
milliseconds, the tenth one's docstring is not what gets read.

So the question to ask about any argument is not "is the unit written down"
but "what does being wrong about it cost". `wait_ms=2500` on a click is a
two-and-a-half second pause nobody notices. `wait 2500` was three dead rounds
and an hour of misdirected debugging, because the same mistake, in a place that
holds a lock, is a different mistake.
