# The default that could spend your money

`co browser go_to example.com` is the first browser command anyone runs. Until
today, on a machine that happened to have Onionwright installed and a little
credit in the account, that command could open a paid session and start
charging $0.025 every fifteen minutes. Nobody had asked for the paid browser.
They had asked for a web page.

The mechanism was `--engine`, which takes `auto`, `system` or `onion` and
defaulted to `auto`. `auto` meant "use the paid Onion browser whenever its
preflight succeeds, otherwise fall back to system Chrome". That is a sensible
sentence in isolation. It is a different sentence when you notice that `auto`
is also what a command sends when it says nothing at all about engines.

The code said so plainly, in the docstring of the property that reports the
price:

> `auto` resolves to the paid engine whenever preparation succeeds, so an
> ordinary command can start a billable session; spending money without saying
> so in the output is the part of that which is wrong however the default is
> settled.

That comment is from #1327, which found the problem, fixed the silence, and
left the default itself for someone to decide. This is that decision: nothing
charges unless the caller writes `--engine onion`.

## The fix that looks right and isn't

The obvious change is one character of the CLI: make the `--engine` option
default to `system` instead of `auto`. It is one line, it is easy to review,
and it does not fix the problem.

An Agent driving a browser does not go through the CLI option. It constructs
the browser core directly, and that constructor has its own default:

```python
engine_mode: str = browser_engine.AUTO,
```

Change only the CLI and every human typing `co browser` is safe while every
agent using the browser tool still resolves to the paid engine. The thing
being defaulted is not the flag. It is what `auto` *means*.

## Why `auto` survived

The tempting follow-up is to delete `auto` and leave two honest modes. Reading
the client is what stopped that. `auto` is not only a user-facing choice: it is
the wire value for "the caller named no engine". The client omits `--engine`
entirely when the mode is `auto`, and spawns the daemon without one:

```python
if engine_mode != "auto":
    request_kwargs["engine_mode"] = engine_mode
```

A browser daemon is pinned to the engine it started with and refuses to swap
engines while warm — for good reason, since the alternative is a session whose
billing changes underneath it. So if every ordinary verb started sending an
explicit `system`, then `co browser --engine onion go_to ...` followed by a
plain `co browser get_text` would stop working: the warm paid daemon would
refuse the second command as a hot swap. The multi-step paid workflow would
need `--engine onion` typed on every line.

Keeping `auto` as the wire sentinel and changing where it *resolves* keeps that
workflow intact. A cold start with no engine gives you system Chrome. A paid
session you opened on purpose keeps serving the verbs that follow it.

## What was checked before changing it

Two things could have made this change break something quietly.

The remote browser needs the Onion engine to exist — its egress gateway has no
meaning without it — so if that path relied on `auto` reaching the paid engine,
this change would have broken it. It does not: the private daemon has always
demanded an explicit `onion`, and a test asserts that both `auto` and `system`
are rejected there before any runtime is created.

And `Resolution.fallback` was defined as "requested auto, resolved system",
which after this change would be true of every ordinary command. A status field
that reports a failed paid attempt on a run where nothing was attempted is
worse than no field, so it now excludes the plain default.

## The shape of the lesson

A default is not the value written next to the flag. It is every path that
reaches the code when nobody made a choice — the CLI option, the library
constructor, the wire value for "unspecified". Fixing the one you can see is
how you ship a fix and keep the bug.
