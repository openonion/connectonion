# Evaluation Is a Choice

The clue was not a dramatic bill. Across one measured five-step run, task
evaluation cost $0.15 out of $10.73—about 1.4 percent—and another run recorded
none. That is too small to build an argument around.

The stronger evidence was on disk:

```text
~/.co/evals    2,311 records    281 MB
```

The oldest record was six months old. Nothing pruned the collection, and the
operator had never asked `co ai` to evaluate every task.

Two mechanisms had been hidden behind the same word. The `eval` plugin is a
debugging judge: it generates an expected outcome and scores the completed task,
using two additional model calls. The Logger independently records sessions
under `.co/evals/`, whether or not that plugin is installed. Removing the plugin
from the default fixes the unwanted calls, but it does not reclaim or bound a
single byte. Treating them as one bug would have fixed only the visible half.

`co ai` now leaves the judge off unless the operator passes `--eval`. Direct
library use remains explicit as it always appeared in the documentation:

```python
Agent("assistant", plugins=[eval])
```

Session records remain available for replay and diagnosis, but generated
records now have a count boundary: the newest 500 survive, along with their
bounded per-record runs. Authored eval suites are a different class of data and
are never pruned.

The design lesson is modest: observability and judgment are not free merely
because they run after the work. Debugging machinery should announce itself,
and historical artifacts need an ownership and retention boundary on the day
they are introduced—not after the hidden directory reaches hundreds of
megabytes.
