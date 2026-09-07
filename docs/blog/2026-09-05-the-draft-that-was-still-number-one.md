# The draft that was still number one

The agent had just listed Gmail drafts. Its next command used a number, as the
CLI invited it to do. That seemed harmless until an empty listing entered the
same workflow.

The command printed that there were no drafts. But its local numbering cache
still held the previous result. Asking for draft one could reach an older draft
even though the last output said there was nothing to choose.

We first looked at the listing text. Making numbers visible in piped output had
already corrected an output-only model test that chose row zero. This failure
was different: the text was true. The hidden state that interpreted the next
command was stale.

An empty result now replaces the numbering cache with an empty mapping. The
regression starts with an old row one, returns no drafts, then tries to resolve
one again. It must not recover the old ID. A draft returned by creation has its
own ID; it does not become row one simply because it is new.

That changed what we watched during the audit. A successful command was not the
end of the test. We had to follow the next reference it left behind. Otherwise
the CLI could tell the truth in one response and make the next action wrong.
