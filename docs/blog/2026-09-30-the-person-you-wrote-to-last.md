# The person you wrote to last

The notebook's daily round had one job it never did. After it caught up on
new mail, it was meant to investigate one unfinished page. On the owner's
notebook it tried the most-mailed contact, 185 mails, and gave up because the
page did not fit the day's calls. Then the home workspace, 813 sessions. Then
the connectonion project. Every day it tried the same three and wrote nothing
(#1723). The pages that mattered most were exactly the ones too big for a day.

Earlier today #1942 fixed the size of one investigation. Instead of
summarising every mail before writing a word, the gathered mail goes into
files and one model turn searches them. So this stage began with a simple
plan: build a people agent that searches a prepared folder. We built it, ran
it on the same 157-mail correspondent #1850 had measured at 8.2 million input
tokens and 3 hours 24 minutes, and it wrote his page in 0.67 million.

Then the turn. #1942 had landed while we were measuring, and it did the same
thing for every kind of page. Two ways to investigate a person would drift
apart within a week, as the notebook's page shapes once did. So we threw our
pipeline away and asked what #1942 did not do. The answer was the round
itself: who comes next, how much of their mail to read, and when.

Who comes next is now the person the owner wrote to last. People mailed in the
last two weeks go first, then everyone older, newest first, because last
week's relationship is the useful one. How much to read changed too. A page
that was investigated before is read only from the mail since then, so a
correspondent who sends two lines on Tuesday costs two lines, not five months
again.

When is the four-run day the owner asked for. The first run of the day
finishes unfinished pages, most recent first. Every later run lists the
mailbox once since the run before, finds who wrote, and updates only those
people, and only the projects with new messages the owner typed. A run with
nothing new costs nothing.

We measured the result on the same man with #1942's pipeline: one call, 1.93
million input tokens, 15 minutes including fetching 265 mails and 99
attachments, and a page with 88 citations. His role, which appears in only two
of those mails, was found. That is four times cheaper than the baseline and
thirteen times faster, and it fits a day.

The lesson is about where to stop. Our own pipeline was cheaper still, and it
was the wrong thing to ship. The order and the window were what the round
lacked, and they work on top of the one investigation everyone else uses.
