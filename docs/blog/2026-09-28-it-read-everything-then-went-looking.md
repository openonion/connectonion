# It read everything, then went looking

We wrote eleven test cases for the two skills that write a person's page and
a project's page. The cases were a client with a signature block, a partner
who writes in Chinese, two people both called Mia, a forwarded mail full of
someone else's claims, a calendar invite and nothing else, a mail that tells
the AI to record a false debt, and five projects, one of them a plan that was
never deployed and one with an API key pasted into a session.

On the first run half the cases failed, and none of them failed on a fact.
The agent read the page and the material in its first two steps, which was
everything it needed. Then it spent its remaining thirteen steps looking for
something to copy. It opened other cases' finished pages, the run log, git
history and three other skills, and it ran out of steps before writing a
word. The skill never said that the two files it had just read were the whole
input.

One paragraph at the top of each skill fixed that: read what you were given,
then write, and look elsewhere only for a gap you can name. The same run then
passed five of six people and four of five projects. Codex does the same
thing in production, where it spent a dozen turns stitching material back
together before writing a page.

The rest were smaller, and each one came from reading what the agent had
done. A person with one calendar invite got "no prior history" written into
every section instead of `Unknown`. A person whose material mixed in a second
Mia lost her own email address from the page. Three of the fixes were to the
test setup rather than the skills, because the agent found the grading script
and ran it, and a second run of a case found the first run's page.

Two of the problems were in our validator, which is what decides whether a
real page is saved. It refused a flow diagram drawn with `│` and `▼`, and it
read `[1, 2]` as no citation at all, so four of five good project pages would
have been thrown away. After seven rounds every person case passed on both
runs, every project case passed on both runs, and the validator accepted all
eleven pages.
