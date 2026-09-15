# The search that had already happened

A `grep()` that takes twenty-six minutes and then gets killed does not look like a bug.
It looks like the model being slow, or the machine being busy, or a round that was
always going to be tight. The round it happened in reported nothing unusual: it simply
stopped at iteration 2 and never mentioned why.

What the tool actually did was simple enough to be embarrassing. Asked to search a
directory, it walked the whole thing first and decided what to ignore afterwards:

```python
files = list(base.glob("**/*"))
files = [f for f in files if f.is_file() and not _should_ignore(f) and _is_text_file(f)]
```

`_should_ignore` knew about `node_modules`, `.git`, `target`, `.venv` — thirteen
directories' worth of hard-won knowledge — and every one of them was consulted only
after the walk had finished. The filter was correct and completely useless. A search
from `$HOME` entered every project, every `Library`, every cache, in-process, with no
cap and no timeout, because the only barrier was a sentence in a prompt asking the
model not to grep directories. The prompt lost. It had lost twice.

The fix is two lines of shape and one of them is the whole lesson: prune `dirnames`
**in place**, inside the walk, so the ignored subtree is never entered rather than
entered and discarded.

```python
for dirpath, dirnames, filenames in os.walk(base):
    dirnames[:] = [d for d in dirnames if not _is_ignored_dir(d)]
```

The second half is a cap on how many candidate files the walk will collect, because
pruning bounds the common case and not the pathological one — a directory with no
ignored children still walks forever. When the cap trips, the walk stops and says so.

That "says so" turned out to be the part worth keeping. An unfinished walk that returns
"no matches found" is indistinguishable from a finished walk that found nothing, and
the second is a legitimate answer that must stay legitimate. So the truncation note is
emitted even when there are no matches at all: an empty result from a walk that stopped
early must never be allowed to look like an empty result from a walk that finished.
That was the failure mode in the report — a killed call with no diagnostic — and it is
the one thing a cap could plausibly make worse if it were written the obvious way.

What the tests pin down is the mechanism and not the output: one test monkeypatches
`Path.glob` to raise, so the day someone reintroduces an eager materialisation the
suite says so by name; another checks that a capped search with zero hits still reports
the cap. Reverting only the collection block back to `base.glob("**/*")` fails exactly
those two and passes the other two — which is the shape a regression guard should have.

The `max_depth` argument the issue mentions as "ideally" is deliberately missing. There
is no default in the issue, and silently changing how deep a search goes would break
the deep searches that are supposed to work. A vague improvement is worse than a
missing one.
