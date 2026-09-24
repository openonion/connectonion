# The TikTok half was waiting on a page nobody had seen

In early September a draft PR tried to give `co` two creator commands at once:
`co youtube`, over the official Data API, and `co tiktok`, driven through a
browser tab. Three weeks later the YouTube half is in the product and the TikTok
half was still sitting on a branch with a red CI check. This week I picked the
branch up to finish it. Most of the work turned out to be deciding what "finish"
could honestly mean.

The first surprise was that there was less to carry than the diff said. The PR
listed 35 files and three thousand lines. But the owner had split the Google
work out into its own PR the same day, and that one merged. So every YouTube
file on the old branch was an older copy of something main already had, and
main had moved on: YouTube's usage errors now go to stderr with the same
recovery tip as every other `co` command, and the missing-login code is
`not_configured`, not `auth_required`. A test file written against the old
branch failed twelve times on current main. None of those failures were bugs.
They were the old branch disagreeing with decisions that had already been made.

The second surprise was the red check. The Python 3.10 job had not failed on
anything in the PR. It had timed out in `test_scroll.py`, which patched
`time.sleep` for the whole process. A session-cleanup thread left behind by an
earlier test was looping on that sleep, and with the sleep gone it became a busy
loop that starved the test runner for five minutes. Main had already fixed both
halves: the patch is scoped to the scroll module now, and the cleanup thread
stops with its app. Nothing in the TikTok code needed a 3.10 change.

That left the real question. The old PR had been honest in its body: on
5 September the TikTok Studio upload URL redirected to a login page, so nobody
had seen the upload form, the caption editor, the privacy choices or the
publish button. `co tiktok post --confirm` checks the plan's digest and then
refuses with `submit_unavailable`. It was tempting to "finish" by writing the
submit step. It would have been a publish button built from guesses and tested
against a page I wrote myself. That is the kind of feature that passes CI and
posts the wrong video.

So the finished version is smaller than the one I set out to write. `post`
seals a plan: the file's bytes, the caption and the intended handle, hashed so
a changed file cannot ride on an old approval. `inspect` saves a screenshot and
the page context before reading anything, then proves a login page is a login
page and says so, instead of calling it ready. The skill is TikTok-only now,
because YouTube has a home in the Google skill. What is still missing is the
part that needs a real account: seeing the form, then writing the adapter.

The lesson I keep relearning with stranded branches is that the diff is not the
work. Half of this one had already shipped under another name, the red check
belonged to a bug someone else had fixed, and the most important line in the
remaining half was the one that refuses to post.
