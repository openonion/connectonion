# The fix that only covered one kind of page

Yesterday's fix for the refused project page worked. The 1.9.0a7 acceptance
run took the connectonion page from 24,586 characters to 18,671 in one turn,
and the review accepted it. Then the same run did the same thing to a person.

Ody Zhou's page was 18,730 characters. The daily round gathered four days of
mail and wrote a page of 20,493. The review refused it, and 643 thousand input
tokens bought nothing. A few minutes later we investigated Ody by hand, as a
user would after seeing "refused". The gather found the same mail: 113,335
characters of material against 113,429 the first time. That turn spent 933
thousand tokens and landed at 19,912, 88 characters under the limit. The next
mail would push it over again.

Nothing in the fix was wrong. It was in the wrong place. The project-page
writer owned its own prompt, so that is where the size note went, and where a
refusal was remembered. Person, org and skill pages go through the
investigation runner, which never heard about either. The limit itself lived
in the shared review, so every kind of page could be refused, but only one
kind was warned beforehand or remembered afterwards.

Now the size note belongs to the review module that enforces the limit, and
the runner adds it to every one-page turn. A turn reads "The page is 18,730
characters; it must end under 20,000" before it starts writing. A refused
investigation records the source ids it was given. If the next gather finds
nothing beyond them, the run stops before the model call and says the page
waits for newer material. A timeout or a crashed harness is not a refusal, so
those are retried as before.

The same run turned up a smaller version of the mistake in the queue. It still
counted only "investigated" as a pass, so a page sync had written that morning
ranked first as "not investigated". And github.com led the organisations with
six people, every one an unsubscribe address the people queue already ignored.
In both places a rule existed in one module and was missing from the one
beside it.
