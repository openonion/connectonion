# Told the limit before the work

1.9.0a7 fixed a loop: a project page over 20,000 characters was refused every
night for the same reason, at about 260 thousand tokens a time. The next
acceptance run, on a copy of the owner's notebook, found the same loop one
door down. A person page and an organisation page, both close to the limit,
were investigated, came back a little over it, were refused, and were picked
again the next run with the same mail. 643 thousand tokens, then 933 thousand.

We had fixed the project path and not the shape of the bug. Two things were
true on every path. The model was judged against a limit nobody had told it,
and a refusal left no trace, so the scheduler asked the same question with the
same material and paid for the same answer.

1.9.0a8 fixes the shape. Every turn that writes one page, whether it is an
investigation or a maintenance pass, is told the page's current size and the
limit before it starts. A refused investigation records the sources it was
given and does not run again until new mail arrives for that subject. A
timeout or a crash is still retried, because those say nothing about the
material.

The lesson: when a bug comes back on a neighbouring path, the first fix
treated an instance. Find what all the paths share, and fix that.
