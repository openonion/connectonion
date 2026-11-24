# The preview names the page by id

*2026-11-24*

Writing to Notion from the terminal is four commands: `create` a page under a
page, `append` to the end of one, `add` a row to a database, `update` the
fields of a row. Each reads its target first, prints what it would send, and
changes nothing until `--yes`. That much followed the rule every co write
already keeps. The question this change had to answer was what `--yes` points
at.

Lists are numbered, so `co notion update 3 --set Status=Done` is the natural
thing to type. A number is a row of the last list shown, and between reading
a preview and typing `--yes` a person, or an agent, may list something else.
On a read that costs a wrong page on screen. On a write it is a wrong row
changed, and Notion has no undo for us to call. We saw how short that gap is
while testing: one `db` command between two others moved every number.

So a number previews, and the preview's `Next:` line is the same command with
the page's id and `--yes`. What gets written is what was shown. `--yes` with a
bare number is refused and says to use the id the preview printed, or the row
with the `--listing` it came from. This is the rule `co asana update` already
follows; the reason is the same.

The rest is about not writing twice. Notion takes at most 100 blocks and about
500 KB in one request and 2,000 characters, measured in UTF-16, in one piece of
text. Long content is split before the preview, so the preview shows the
blocks that will be sent, and the batches go one at a time, each confirmed
before the next. If one fails, the error says how many blocks are on the page
and gives the `--start-at` command that resumes after them. A read that times
out is retried; a write that times out is not, because Notion may have done it.
It is reported as "may or may not have been made", with the read that tells.
