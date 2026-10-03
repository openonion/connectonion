# Opening a written notebook

The first ten-year REM map could be opened in a few seconds after the a25
changes. A different notebook with 227 written pages still took about 49
seconds to reopen. That matters after the first run: each visit to the local
reader rebuilt its private HTML snapshot before the browser could show it.

Profiling that notebook found two repeated jobs. Relationship navigation ran
roughly 1.5 million regular-expression searches: each written page was checked
against every known person, organization and project name. The reader also
parsed entire cited PDFs to display at most 640 characters in a source dialog.

The relationship pass now checks for a case-folded literal first and runs the
original boundary-aware expression only when the name might be present. Dotted
and dotless I keep the expression path because Python's case-insensitive
matching accepts forms a plain literal check could miss. The PDF source
preview stops after it has enough text to know both the excerpt and whether it
is truncated. Investigation still reads full attachments when it needs them.

On the same private 810-page notebook, the 2,406 relationship results had an
identical digest before and after the change; relationship time fell from 18.09
to 0.53 seconds. All 738 cited source contexts also had an identical digest;
that pass fell from 9.35 to 5.36 seconds. Full private HTML rebuilds took
8.39, 9.65 and 8.43 seconds in three local runs, compared with the earlier
49.44-second review measurement. The output remained mode 0600. These are
one-machine measurements, not a general speed guarantee.

The next review opens the actual written reader on desktop and phone, checks
an investigated page, citation dialog and privacy controls, then repeats the
timing after future source or relationship changes. The larger first-run goal
still requires a live model batch and a source-by-source memory review.
