# The reply that was there

*2026-11-15*

Seven of the REM reader's browser tests had been red on main for days. Nobody
was chasing them, because CI does not run them and each one failed for a
reason that looked like its own fault: a button order the test still expected
from last week, a subtitle that had been removed on purpose, a timer set to the
year 2099.

Five of the seven were exactly that, stale tests. We brought them up to the
current rules and moved on. The sixth was a real bug: on the Sessions page, a
private day you had chosen to reveal closed again whenever the page redrew.

The seventh was the interesting one. The test asks Claude to talk a Today row
over and waits for the answer to appear in the page. On main it failed at its
first step, on the stale button order, so its second half had not run since
the row's actions were rearranged. Once the first step was fixed, the second
half ran, and timed out. We could not tell from the failure whether the page
or the test was wrong, so the engineer added three prints instead of a guess:
what the page posted, what the worker's file said, and what the page showed.

The post returned 200. The worker's file held the context and Claude's reply,
state idle. The page showed nothing at all. The reply was there; the page had
reloaded after the request and forgotten which conversation was open. Handing
a row to an agent survives that reload because it rebuilds from saved
receipts. Talking kept its panel only in memory. Now the reader saves the
begin request and reopens the same conversation before it rebuilds the rows.

A test that fails early protects nothing after the line where it fails. The
first failure was cosmetic and the second was a feature that did not work, and
the cosmetic one had been standing in front of it.

The same release fixes why our own test runs printed no summary on one Mac: a
process-listing guard decoded `ps` output strictly, and `ps` had cut an app's
Chinese name in the middle of a character. And it carries what a walk through
a real notebook showed that the demo data could not: a table cell that grew
six lines tall, an organisation page that opened with "Unknown, not
investigated yet" as if that were a fact, and a contact date the reader had
and did not print.
