# The page that survived its review

The reviewer returned “approved.” The regression test expected the update to be
blocked. That disagreement was the useful part of the Control Center test: the
reviewer's answer described a page that no longer occupied the build directory.

The fixture started with a deliberately dull page, `<h1>first</h1>`. The runtime
reviewed it, uploaded it, and recorded it as active. Then the test wrote a second
page and asked for another update. Inside the review callback, before returning
approval, it overwrote the file again with `<h1>third</h1>`.

There were now three things an implementation could confuse: the page already
visible to the user, the page passed to the reviewer, and the page currently on
disk. All three had the same filename. An implementation that treated approval
as permission to upload that filename would serve the third page with the second
page's approval. Another implementation could clear the active app while waiting
for review, leaving the user with neither the old page nor a usable replacement.

The test made the expected result concrete. The update had to report
`source_changed`. The active descriptor had to equal the descriptor saved before
the attempt. The uploader's call count had to remain one: the original page was
the only page it should ever have received.

That forced the runtime to keep two records instead of overwriting one status.
The latest attempt can fail while the current app remains approved. Before the
review begins, the runtime captures a bundle and hashes its manifest. Review and
upload receive that captured object. A later read checks whether authoring has
continued; it does not silently replace the bytes under the review result.

Keeping the old descriptor raised the next question: would it survive other
failures, or only the one we had just arranged? The companion test sends the
attempt through a blocked verdict, a malformed result, a review timeout, an
upload timeout and a mismatched revision receipt. Each path has the same final
assertion: the original active descriptor remains intact. The browser fixture
then checks the visible consequence. A blocked finding appears above the invoice
app, while the previous invoice app stays on screen.

Rollback exposed a limit to that promise. Saving an old URL is easy. Promising
that it still names available, approved bytes is harder. The restart test restores
a previous revision, then changes the availability check and expects restoration
to fail. It also changes the review policy and refuses the old approval. Keeping
a page in history cannot make a removed artifact available or make yesterday's
policy current.

There is a cost to this behavior. A changed build must wait for another review,
and retained revisions consume storage. A failed update can leave the user on an
older page. Those are visible states the interface can explain. Serving newly
changed code under an earlier approval would hide the failure instead.

These are local regression and browser-fixture results for the 1.8.4 preview;
they do not claim production hosting acceptance. The page that survived this
review was the first, unremarkable page. Keeping it visible was the test's proof
that “approved” still referred to particular bytes.
