# One page held back the rest

The Wiki's background upkeep reads new material in batches. It hands each
batch to a model, which updates the pages that material touches, and then
moves a cursor forward so the next run starts where this one stopped. That
cursor only moves when the batch is accepted.

On a real notebook, one batch touched three pages: two people and a project.
The two people pages were fine. The project page was missing its overview
diagram, which the project template requires. The rule was that a batch is
accepted whole or refused whole, so the batch was refused and the cursor
stayed where it was. At three the next morning the schedule ran again, read
the same batch, got the same three pages back, and refused them again. The
upkeep had not crashed. It was stuck, and the only sign was a daily log line
saying `failed`.

All or nothing had seemed like the careful choice: never write half an
update. But the batch wasn't one update. It was three, and they didn't
depend on each other. Refusing all three kept one flawed page out of the
notebook, and cost the notebook every later batch.

So pages are now accepted one at a time. A page that passes review is
written. A page that fails keeps its old text, and the model's version is
saved beside the run with the reason it was refused. The cursor moves on.
Nothing is lost for good: investigating that page reads every source again,
including the one that caused the problem. One case is held back on purpose.
If the batch carried a correction the user wrote about the refused page, that
correction stays in the queue, because a correction the user typed should not
disappear because the model mishandled it once.

The same run found the daily investigation stuck in the same way. It always
started with the person the owner writes to most, and that person needed more
model calls than the day allowed, so the round failed every day and updated
nobody. The check happens before any model is called, so the fix costs
nothing: move on to the next page.
