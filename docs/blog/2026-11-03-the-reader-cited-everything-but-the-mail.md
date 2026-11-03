# The reader cited everything but the mail

A notebook a few weeks old, 985 pages, opened in the browser. The home page
took a minute and a half to answer. When it arrived, it said "First build:
your notebook was just built". Clicking a source under a claim drawn from an
email opened a panel that said the snapshot did not include the original.
That was true of every one of the 960 mail citations on the notebook.

All three were the reader doing reasonable things at a size no fixture had.

The page cites lines its owner typed into coding sessions. Each one is a line
in that project's JSONL, and each lookup read and split the whole file again.
At 6,452 citations that was 76 of the build's 127 seconds. The split lines are
now kept per file while its size and modification time are unchanged.

The original text behind citations shares one budget, 1.5 million characters,
and it was spent in id order. Session pages list every typed line under
Sources: more than 8,000 of them. `claude-code:` and `codex:` sort before
`gmail:` and `outlook:`, so the budget was gone before the first email. Now a
claim's numbered sources come first, mail first among them, and session
source lists take what is left. The owner's own reader gets 3 million. On the
same notebook 933 of 960 cited mails open their original, and the page is
11.8 MB instead of 16.5 MB, because thousands of excerpts nobody clicks are no
longer inside it.

"First build" was an inference from absence. The page carries the latest 20
runs. When none of them is older than the latest pass, the notebook must be
new. A day with 33 runs meant all 20 sat inside that pass. The page now also
carries when the first run started, and the brief compares against that.

Each fix has a test that fails without it: a file read 40 times instead of
once, a mail citation missing from a small budget, and an old notebook called
new.
