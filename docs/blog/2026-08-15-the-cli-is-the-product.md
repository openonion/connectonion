# The CLI is the product

*2026-08-15 · Design Journal*

For several months, ConnectOnion accounts have been able to send credits to each
other. `POST /api/v1/transfers` worked in production. `GET /api/v1/transfers`
returned clean history. Onboard verification was built on top of it. The
feature was live, tested, and billing real money.

It also, for every user we have, did not exist.

Nothing in `co --help` mentioned transfers. No command called the endpoint. The
only way to move credits was to hand-sign a request against the API — which is
to say, the only users of the feature were the people who built it. A working
backend with no CLI in front of it is not a shipped feature; it is a rehearsal
for one. The library is the engine, but the skill and the CLI are the
interface, and users — human or AI — live entirely on the interface side.

This release closes three gaps of exactly that shape. Each one is small. What
makes them worth a journal entry is that all three were invisible from where we
usually stand.

## An error that names a problem no command can answer

When multi-address accounts shipped, `co email send --from` gained a guard: try
to send as an address you don't own and the server answers 403 with

```
❌ Failed: nobody@mail.openonion.ai is not one of this account's email addresses.
```

That message is accurate, specific — and a dead end. It names a category
("this account's email addresses") that no command in existence could list.
The backend's `list_email_addresses()` was live; the CLI never called it. An
agent hitting that error had nowhere to go but guessing, and an agent that
guesses email addresses is an agent you eventually have to apologize for.

The fix is `co email addresses`, and one sentence appended to the 403: `See
your addresses: co email addresses`. The error is now a fix-it guide. That is
the whole standard we're trying to hold: every failure message should read as
the first line of its own recovery procedure.

## Tips that hid from the callers who needed them

Our listing commands end with a next-step tip — `Read one with: co gmail read
<#>`. The tip lived inside `if console.is_terminal:`, so piped output didn't
get it. That guard felt reasonable when it was written: pipes are for scripts,
scripts don't read prose.

Except the callers who pipe are AI agents, and they do read prose — it is the
only thing they read. A human in a terminal has habits, history, and the
memory of yesterday's session. A fresh agent has the output in front of it and
nothing else. We had built discoverability for the audience that needs it
least and stripped it from the audience that needs it most, and no manual test
could ever catch it, because a human tester is by definition in a terminal.

## Measuring the tips instead of admiring them

The `cli-skill-design` methodology gives tips an actual test: hand a fresh,
text-only model one command's output and a goal, and ask for the single next
shell command. No SKILL.md, no `--help`, no history — those are the crutches
the tip exists to replace.

The first run across the mail surface scored **5 of 8**. The three failures:

- A piped inbox printed no tip at all, and the model invented `readmail 18f2a`.
- A failed send said `Retry the same command with --idempotency-key <key>` —
  but "the same command" is not in the output, so there was nothing to
  reconstruct the retry from. The model replied `!! --idempotency-key k-123`.
- The stale-number message said `run co gmail to refresh` and stopped one step
  short of the goal. The model replied `co gmail && co gmail 3`, the second
  half of which does not exist.

None of these tips looked wrong in review. All of them read fine to a human,
because a human silently fills the gap with context the tip was supposed to
carry. That is precisely why the test uses a model with no context: it can't
be polite about a missing step.

The fixes are one line each. Tips now survive piping. The retry hint restates
the entire command, quoted and copy-pasteable. The stale-number message names
the step after the refresh. On the re-run, all eight tips — plus the new
transfer and addresses tips — produced a correct next command.

## What this teaches

The three gaps share one anatomy: **the engine was done and the interface was
not, and from the engine room everything looked finished.** The transfer API
passed its tests. The ownership 403 was correct. The terminal tips worked for
everyone who tried them by hand. Every instrument we normally read said green,
because every instrument we normally read measures the engine.

The interface has its own instruments, and they are unforgiving in a useful
way: does `--help` name the capability? Does the failure name the next
command? Does the output, alone, carry a fresh agent to the right next call?
Those questions have runnable answers, and running them found real defects
that review had blessed.

So the rule we're keeping: a feature ships when the CLI exposes it, the errors
route around themselves, and the tips pass the test — not when the endpoint
returns 200. The skill and CLI are the interface; the library is the engine.
Nobody buys an engine.
