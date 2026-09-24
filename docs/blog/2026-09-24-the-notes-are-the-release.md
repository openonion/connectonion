# The notes are the release

At 12:27 on 24 September, 1.8.8b7 was ready: a version bump, a reviewed
screenshot of a skill benchmark going from 0/5 to 5/5, and notes explaining
`co benchmark` and `co browser network`. It sat there while main kept moving.
By the evening six more pull requests had merged behind it: Discord and
Telegram inboxes, TikTok post plans, Gemini image output, an Outlook fix that
stops the same email going out twice, and the labels that mark all of those
experimental.

The obvious move was to merge the prepared branch and tag it. It would have
worked, mechanically. The release workflow builds whatever commit the tag
names, and the merge commit held every one of those six changes. PyPI would
have published them all under notes that mentioned none of them.

That is the failure the tag-driven process exists to prevent, arriving from a
direction it does not guard. Nobody publishes from a workstation, the tag
points at a reviewed commit, the version agrees in four files — and still the
thing a person reads before upgrading would have been wrong. For a preview
that is how someone ends up with a new `co discord` command they never agreed
to try, or never learns that Outlook stopped resending mail after a 504.

The prepared branch had a second problem: it was cut from the b6 tag, so its
own head lacked the two features its notes described. There was no commit
where the notes and the code matched.

So b7 was folded rather than shipped. It had never reached PyPI, so the number
was free to reuse with no gap. One release PR now carries the benchmark notes
and their capture from the first preparation, and a section for the six
changes after it, including what is left out and why: `co whatsapp-cloud`
waits on a backend route that is not deployed. A second capture is a live run
of this commit's `co --help`, so the picture of the experimental labels comes
from the code being tagged, not from a description of it.

The rule we took away is small. Before tagging, read the notes against
`git log` from the last tag to the commit being tagged. If a merged change is
not in the notes, it is not ready to tag, however green the checks are.
