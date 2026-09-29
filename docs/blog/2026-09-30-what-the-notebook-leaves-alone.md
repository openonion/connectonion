# What the notebook leaves alone

After the map names were fixed, the owner's notebook still had 43 people pages
whose title was an email address. Nobody had written to any of them. They were
receipts, sign-in notices and newsletters, and the queue ranked them next to
colleagues. They sat at the bottom, but a long enough first pass would have paid a
model to research a mailing robot.

Deleting them would have been the quick fix, and the wrong one. Among 43
nameless senders there can be a real person who has not introduced
themselves yet. So the rule is narrower. A page titled with an address that
the owner has never written to is **held for review**: it stays on disk and
links still work, but it is left out of the investigation queue, `co wiki list`
and the reader's contents. The page comes back on its own when a later map
finds a name or a reply. `co wiki list people --review` shows what is held,
and investigating one of those pages brings it back straight away. An address
you have written to is a correspondent, and it is never held.

The same thought applied to maintenance. Each page turn re-sends the page
together with its material, about 110k tokens, and in one measured batch two
of the three turns changed nothing. Nights with no new material also left a
run in `co wiki logs`. So a page that already cites every message pointing at
it no longer gets a turn, a night with nothing new calls no model and leaves no
run in the logs, and `logs --usage` now shows how many pages changed per 100k
input tokens.

The third change covers the model itself. The default model name stopped
working overnight for ChatGPT logins, and five runs failed on it in one
day. A rule like "the newest generation's cheapest model" would break the
same way. Now `co wiki config set model` runs one investigation on a small
built-in fixture page and records what the model actually did. A model that
drives tools gets the agent tier. A model that can only reply gets the summary
tier: Python hands it the evidence, and it answers with the page. The model's
name doesn't enter into it.

All three changes follow one idea: work out what is actually there before
spending anything on it.
