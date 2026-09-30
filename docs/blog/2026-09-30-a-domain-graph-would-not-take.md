# A domain Graph would not take

The fix for slow organisation pages shipped in 1.9.0a3 with one sentence in
its pull request marked as unverified: whether Outlook's search accepts a bare
domain. The tests used fake mail clients, and a fake accepts whatever you tell
it to.

The acceptance run on the owner's notebook answered within a minute. Every
organisation investigation failed in one to three seconds. Asked for
`participants:unsw.edu.au`, Microsoft Graph returned HTTP 500. So did
`participants:@unsw.edu.au`. A full address worked, and so did the first label
on its own: `participants:unsw` returned 152 messages. Gmail's `from:` and
`to:` take the bare domain; Graph's search does not.

The failure was worse than the query, because of what happened next. The 500
was reported as a credential error, although nothing was wrong with the login.
It ended the whole investigation before Gmail was asked, although Gmail would
have answered. And its next step said to run the same command again, which
would fail the same way forever.

Now each server is asked in the form it takes: Gmail gets the domain, Outlook
gets its first label. The loose answer is still filtered to mail on the domain
itself before anything is read. If one mailbox fails anyway, that failure
becomes a line in the page's coverage and the other mailbox is still read.
Authorization failures still stop the run, because only the owner can fix
those.

The lesson is about which assumption a test can hold. The fake in the old test
agreed with our assumption, so the test encoded it. The new fake behaves the
way Graph did on the real mailbox: a 500 for the bare domain, rows for the
label. That makes it a record of what the server did, not a copy of what we
expected.
