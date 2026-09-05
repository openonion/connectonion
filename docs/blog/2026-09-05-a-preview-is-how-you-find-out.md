# A preview is how you find out

1.8.1 was ready to be a stable patch. The version was set, the entry was
written, the tests were green. Cutting it would have taken one tag.

It ships as `1.8.1a1` instead, because the two changes in it are the kind you
want someone to run before you call them finished.

## What is in it

The relay seal makes a relayed session opaque to the relay. And the paid
browser stopped being something you could buy by accident: `auto`, which is
also what a command sends when it names no engine, used to resolve to the paid
Onion browser whenever its preflight succeeded. Now it resolves to system
Chrome, and `--engine onion` is the only way to spend money.

Both changes are about what happens when nobody is looking: bytes on a wire
nobody reads, and a default nobody chose. Neither has a screenshot. That is
exactly why running it matters more than reading the diff.

## The rule that nearly stopped it

The release workflow refuses a preview while any forward-port ledger is open.
The rule exists because a fix that lands on `main` and never reaches the stable
line is a fix that quietly stops being true for the people still on that line.

The open ledger was #1407: a replay-ledger self-heal that 1.8 got and 1.7 had
not. That was not paperwork. A 1.7 host keeps one-use signature digests in
`.co/replay.sqlite3` and created that schema exactly once, at startup, so any
deploy that replaced the file left an empty database behind. Every later signed
call raised `no such table: used_signatures`, and the host refused all
authenticated work while reporting itself healthy — 2h44m of it on the
Melbourne rental host on 2026-09-03.

So 1.7.4 shipped first, with the self-heal backported. `main` fixes the same
outage a different way, by giving a single-process host an in-memory ledger,
which needs a sealed channel 1.7 does not have; the self-heal is the part that
applies to both, and it is the part that moved.

Reading the gate's code rather than its prose is what made the order clear:

```python
def release_needs_clear_forward_ports(version: str) -> bool:
    """Patch publication may proceed; every newer channel requires a clear ledger."""
    return STABLE_PATCH.fullmatch(version) is None
```

A stable patch is exempt. A preview is not. So choosing to preview first is
choosing to clear the ledger first — the stricter path, arrived at by wanting
the safer one.

## A smaller thing, recorded because it wastes an hour

After editing `_version.py`, the version tests failed while the file was
already correct. `1.7.3` and `1.7.4` are the same length, and a `git stash pop`
restored the original mtime, so Python's bytecode cache still looked valid and
kept serving the old string. Nothing was wrong with the change; the interpreter
was reading a file that no longer existed. Clearing `__pycache__` fixed it.

Worth knowing, because the symptom is a test insisting a file says something
you can see it does not say.
