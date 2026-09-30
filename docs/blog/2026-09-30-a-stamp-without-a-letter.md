# A stamp without a letter

This morning the owner ran 1.9.0a2 on his real notebook: 370 people, 29
projects, a week of the daily round behind it. We checked the pages against
his mail, and six facts out of six were right. What was wrong was what the
notebook said about itself.

One page was for a university mailbox. Its status line said "investigated",
and its coverage said eight message bodies had been read. The log said the
digests of those eight bodies had all come back empty: "summarised in 0
chunk(s)". The turn that wrote the page had two things to read, the page as it
stood and our own note listing where we had searched. It spent 919,000 input
tokens on those two things and wrote a page citing them. Then our code added
the stamp, because the run had finished.

That was the pattern all morning. Each part did its own job, and the parts did
not check each other's work. The gather searched and found nothing, and
reported that honestly. The model wrote from what it was given, which was
nothing, and cited it honestly. The validator checked that every citation
pointed at something the run had supplied, and it had: the coverage note
counted as a source. Every check passed, and the page claimed a reading that
never happened.

The fix is to stop earlier. When the gather finds no mail, attachment, session
line or chat message about the subject, the run ends before any model call. It
says what it searched and which `--handle` to try next, and the page is left
unmarked. On the cheap tier, where material is digested before the page turn,
the same happens when every digest comes back empty. The validator got the rule
it was missing: a page whose only sources are itself and the coverage note is
refused. It took the owner's page to show us that we had been treating our own
paperwork as evidence.

The pages already stamped this way needed a different fix, since nobody should
have to edit them by hand. The daily round keeps no per-page coverage, but the
page shows the problem anyway: stamped "investigated", with no Sources entry
naming a message, a session, a URL or a file. On his notebook that was one
page out of five. The queue now treats such a page as never investigated, and
the next real reading replaces the stamp.

The rest of the morning had the same shape. A project page was thrown away
after 199 seconds because one session id in its Sources was mistyped. Now the
line that rests on the bad citation is dropped and the rest of the page stays.
The people queue ranked vendors first because it sorted by the date of the
last mail and nothing else. Now it puts people he has written to first, and it
says that its mail counts come from the map. One person the map counted once
had 617 mails. Two commands listed the queue with two different functions and
disagreed by four people. Now they share one function. And the model's `co ai`
said "Skill 'rem-investigate' not found" after minutes of fetching mail. The
cause was the schedule's `PYTHONPATH=.`, which resolved inside the task folder
and loaded an older connectonion. The path is now absolute, and the Skill is
checked before any mail is fetched.

What we took from it: a status line is a claim, and it needs evidence like any
other claim. "The run finished" and "the run read something" are two different
facts, and the notebook had been recording the first while showing it as the
second.
