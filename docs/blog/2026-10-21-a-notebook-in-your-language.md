# A notebook in your language

REM writes every page in English. That is the canonical record, the one
whose citations are checked. For someone who reads Chinese first, though,
the first thing they saw after `co rem init` was a Chinese interface around
pages that were all English. The translations existed as a separate step,
`co rem translate --all`, which nobody runs on their first evening.

Init now finishes with that step. When the languages detected from your own
sent mail and typed sessions include a non-English one, even as the second
language, init translates every written page into it once the pages are
done. Mapped-only stubs are skipped because there is little to read. The
translations run in parallel on the same workers as the investigations, and
the daily cap that limits upkeep does not apply to this first run. The
estimate printed before anything is spent now includes them: about 80,000
input tokens and 35 seconds per page, measured on a real notebook. Each
translation is also logged as its own run, so `co rem logs --usage` shows
what it cost and later estimates use the notebook's own numbers.

On a trial copy, init wrote six pages and three decisions, then translated
eight of the nine. The ninth was an organisation page whose translation
changed one of the page's source ids, so the check refused to cache it.
That is the check doing its job. The reader's notice now reports "1 page
could not be translated" with the command to retry. Before, it said that
most pages had no Chinese version. A failed translation also no longer
counts as a failed investigation on the home page.

Init also says which languages it found and where it found them:
"Languages: English, 中文 (detected from your sent mail and typed
sessions). Pages are written in English and translated into 中文." It also
says how to change them, and `co rem init --languages zh,en` sets them up
front. Reader settings show the same list with a button that copies the
command to change it.

Commands in the reader got shorter, too. The default notebook gets plain
`co rem start`. Any other notebook under your home folder is written as
`--root ~/…`, outside quotes, since a quoted `~` does not expand.
