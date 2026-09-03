# The Agent That Passed Every Health Check

*2026-09-03*

For two hours and forty-five minutes a production agent answered `/health` with
HTTP 200, held its relay connection open, reported `active` to systemd, and
finished its scheduled crawl on time. It also refused every single signed call:
213 consecutive `misconfigured: replay protection unavailable` errors.

Nothing that watches a service noticed. Everything that watches a service was
looking at the half that still worked.

## Two halves, one process

A hosted agent has two ways in. Scheduled jobs run locally and write straight to
the database — no signatures involved. Remote commands arrive over the relay and
must prove they are one-use, which means consulting `.co/replay.sqlite3`.

Those halves fail independently, and only one of them is instrumented. The crawl
kept landing rows, so the dashboards stayed green and the data stayed fresh. The
liveness probe never touches replay protection, so it stayed 200. From outside,
the agent looked healthy while being unable to accept a single instruction.

That is the part worth carrying forward. A health endpoint that cannot fail with
the subsystem it is supposed to describe is not a health endpoint; it is a
process-is-running check wearing a better name.

## The file outlived its validation

`SignatureReplayStore` checks its ledger in `__init__`. That check ran once, at
`02:38:35`, against a perfectly good file.

At `03:11:43` a deploy synced `.co/` with `rsync --delete` and no protection for
the ledger. It deleted the file and left an empty one at the same path. The
deploy then aborted before its `systemctl restart` — so the process kept running,
holding a path that now pointed at a different, schemaless database.

Every claim after that raised `no such table: used_signatures`, which the store
correctly translated into a fail-closed `ReplayProtectionError`. Correctly, and
forever, because the only code that could have repaired the ledger had finished
running an hour earlier.

Validating at construction assumes the thing you validated is the thing you will
use. For a long-lived process holding a path into a directory that deployment
tooling also writes to, that assumption has a shelf life.

## The empty file was a red herring

The obvious diagnosis is that a zero-byte SQLite file is corrupt and the framework
choked on it. That diagnosis is wrong, and it survived long enough to produce a
first draft of the fix aimed entirely at the wrong place.

`CREATE TABLE IF NOT EXISTS` succeeds against an empty file. Construct a store
over zero bytes and it simply builds the schema:

```python
p.write_bytes(b"")
store = SignatureReplayStore(p)          # succeeds, file becomes 12288 bytes
store.already_used({"signature": "x"})   # False — works fine
```

An empty ledger on disk at startup is harmless. What is not harmless is an empty
ledger appearing *after* startup. The bug was never about the file's contents; it
was about when the file changed relative to the one check that looked at it.

Reproducing the failure rather than reasoning about it is what surfaced this. The
symptom — an empty file and a fail-closed error — was consistent with a story that
was not true.

## Recover where the fault is found

The fix moves recovery to `already_used`, where the missing schema is actually
discovered: rebuild once, retry the claim, and if that fails too, keep failing
closed.

The predicate is deliberately narrow. Only `no such table` triggers a rebuild,
because that alone means the file is a fresh empty database with nothing to lose.
`database is locked` must not, or a busy peer's ledger gets discarded on
contention. Genuine corruption must not either, because a damaged ledger is still
the authority on which signatures have been spent. Both keep failing closed, and a
test asserts that a claim made before a lock still catches its replay afterwards.

Rebuilding forgets what was recorded, so a captured signature could be replayed
until it expires. That window is bounded by `SIGNATURE_EXPIRY_SECONDS` — five
minutes — and it only opens in a situation where the ledger has already been
destroyed by something outside the process. Five bounded minutes of degraded
replay protection beats an agent that answers nothing at all and says it is fine.

## The deployment lesson is the older one

`co deploy` never had this bug. Its first rsync filter is `P .co/**`, with a
comment explaining that it protects "anything a future version writes there"
without requiring anyone to enumerate it.

The deploy that caused this was a hand-rolled fallback that listed excludes by
name instead — and the list did not mention `replay.sqlite3`, because the person
writing it had no reason to know that file existed. Upstream's own history says
the same thing twice: the enumerate-what-to-keep approach lost `.co/skills/` in
its first version and `.co/dashboard.html` in its second.

An exclude list protects what someone remembered. A protect rule covers what
nobody has thought of yet, including the files a future release will add. When
those two disagree, the list is the one that will be wrong.
