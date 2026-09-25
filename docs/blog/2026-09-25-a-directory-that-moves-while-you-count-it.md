# A directory that moves while you count it

One morning the full test suite came back with a single red line: a test
checking that `co doctor` reports how much disk the evals take. Run alone, it
passed. The whole suite, rerun straight away, passed. The issue we filed was
honest about it: we had no assertion text, only a failure that would not come
back when asked.

The easy move with a test like that is to rerun and forget it. The problem is
what that teaches. Next time a real failure shows up in that file, the habit is
already "rerun", and the real one slips through.

So we went looking for what the test depended on that it did not create. The
test built a fake home with forty megabytes of evals and asked for the note. But
the note looks in two places: the home directory, and the evals of whatever
project you are standing in. The test never said where it was standing. Under
the test runner, that was the repository itself.

And the repository's `.co/evals` was not quiet. Other test workers, running in
parallel, were running agents from the same directory, and every agent run
writes an eval and then trims old runs. So while our test was walking that
directory to add up its size, another process was deleting files and run folders
out from under it. List a folder, go to open it, and it is gone:
`FileNotFoundError`.

We stopped guessing and made it happen on purpose. A small script created and
deleted run folders in the repository's evals while the test file ran fifteen
times in parallel. Every one of the fifteen rounds failed, with exactly that
error. Nothing rare about it once the timing was forced.

The fix is two-sided, because the flake was pointing at two things. The tests
now stand in a project of their own, so they only read what they wrote. And the
code itself now skips an entry that disappears between being listed and being
opened. That second part is not a test convenience. A real `co doctor` run next
to a real running agent sees the same trimming, and a diagnostic that crashes
because the thing it is measuring is busy is a poor diagnostic. Something that
is already gone takes no space, so skipping it is the true answer.

With both in place, the same stress ran thirty rounds without a failure, and the
original test file, unchanged, passed fifteen more against the fixed code.

The lesson we keep relearning: a test that fails only sometimes is usually
reading something it did not make. Find that thing, and you often find a real
bug standing behind the flaky one.
