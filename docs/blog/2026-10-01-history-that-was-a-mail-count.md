# History that was a mail count

"History has no value," the owner said, looking at a person page. "And it
looks bad." We counted before arguing. Across their 381 people pages there
were 424 History bullets, and 379 of them were the same machine-written line:
"Observed mail count: 1; first: 2026-07-29; last: 2026-07-29; mailboxes:
gmail. [1]". The citation pointed at `.state/map.json`. On most pages, History
was the only section with anything in it, and what it held was a count.

The pages that had been investigated were not much better. Ody Zhou's History
ran to 17 bullets and 4,300 characters, in date order from July, so the reader
had to scroll past the start of the relationship to find this week. Five of the
17 were "Aaron sent Ody a report". Each bullet was a paragraph.

The count was not useless. The lists in the reader sort people by last
contact, and for a page nobody had investigated, the only date was inside that
History line. So the fix starts by keeping the date and moving it. A mapped
page now leads with "Last contact: 2026-09-06; 6 mails (outlook)." That is
where the reader shows it and where the census already looks for dates. History
starts empty, as the investigation's to fill. `tidy` rewrites the 339 pages
an older map wrote. Some of those older pages had no lead at all, so tidy adds
one rather than let the date disappear.

For the History an investigation writes, the person-page skill now asks for at
most eight milestones, newest first, one line each, where a milestone is
something that changed: agreed, signed, delivered, met. A sent report is not
one. The turn is told the count before it starts, and a History past eight may
not grow. A long one already on a page may come down in steps, so no page is
refused for what it already says. Sources lose their "high confidence,
observed …" prose. An entry is the id and the date, because the claim is
already in the sentence that cites it.

In the reader, History is now a timeline: the date in its own column, the
newest at the top, and only the latest eight shown until you ask for more.
Ody's page opens on 27 September instead of 5 July.
