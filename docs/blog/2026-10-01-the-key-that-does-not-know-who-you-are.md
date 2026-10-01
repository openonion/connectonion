# The key that does not know who you are

The plan for `co canny` fit in one line of the issue: `co canny status <id>
planned --notify`. Canny's API is small and every endpoint is a POST with the
secret key in the body, so a command that marks a request planned and emails
its voters looked like a key, a post id and a status. We wrote the help pages
first, and that line went into them as it was.

Then we read the endpoint. `posts/change_status` has a required field the
issue never mentioned: `changerID`, "the identifier of the admin to record as
having changed the post's status." Creating a comment has the same field
under another name, `authorID`. Canny shows that person in the post's
activity and on the comment. The key opens the whole company, but it does
not belong to anyone, and there is no endpoint that answers "who am I".

The first idea was to find an admin ourselves. Users carry an `isAdmin` flag,
so list the users and pick one. But `users/list` pages through every end user
who ever voted, a hundred at a time, against a limit of 100 requests a minute
on the free plan. A company with fifty thousand voters would spend its
allowance before the status changed. And picking "an admin" means recording
the change under someone who did not make it, which is the one thing the
field exists to prevent.

So the person says who they are, once. `co canny check --email
you@example.com` looks the address up with `users/retrieve`, prints the id,
says whether that user is an admin (Canny only takes status changes from
admins), and prints the `co env set CANNY_USER_ID <id>` line to run. Every
write reads it from there. When it is missing, `status` and `comment` stop
before sending anything and name that lookup command. Reads never need it.

Rate limits gave us the same kind of turn. "Wait for Retry-After, then try
once more" sounded complete, until we noticed the hourly window: a 429 there
can ask for most of an hour, and an agent that obeys will look hung. Now
`co canny` waits up to a minute, and past that it exits and gives the number
of seconds and the command to run again.

The page you read before running a command should tell you what Canny will
record and who it will email. Ours didn't, until we read the endpoint itself
and not just the issue.

The first run on a real account found two things the reference does not
say. The test post we made opened by id, took a status change and a comment,
and never appeared in a listing: `posts/list` returned nothing and the board
counted zero posts an hour later. A second post with ordinary text was listed
at once. The hidden one had no `idea` behind it and no author vote, which is
what Canny's lists are built from; the likely cause is Canny's spam review
reading "[co canny test] ... Safe to delete" as spam. So "not listed" is not
"does not exist", and the docs now say so. The other: the Free plan has no
internal comments. The refusal used to point at the post; now it offers the
same comment without `--internal`, and says plainly that it will be public.
