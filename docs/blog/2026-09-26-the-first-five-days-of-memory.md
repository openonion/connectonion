# The first five days of memory

The first time someone asked Wiki to remember five days of work, it printed
4,800 lines. The terminal looked busy, but the person could not tell what was
ready, what was still missing, or what to do next. Some "projects" were copies
of Wiki's own temporary notebooks. The suggested next command even forgot the
five-day window the person had chosen.

The map now reports counts and a scoped next step in a few lines. It leaves
the detailed record in the private notebook, emits progress while reading
sources, and excludes its own execution folders from project discovery. In an
isolated run, five days produced 46 People, 68 Organizations, five Projects,
and 159 distinct Skill names represented by 400 installed copies. The total
was 519 new pages. That count describes a map, not 519 researched biographies.

The more expensive lesson came next. A full investigation of the owner's page
ran for 45 minutes without a candidate page. It had already used millions of
reported input tokens. We stopped it rather than call that a success. The new
quick first pass reads a bounded sample and must label its coverage as partial;
the full route saves completed extraction chunks so a retry can resume work.
The first quick trial produced a page and explicitly said it covered only 24
of 60 gathered items, though its token use was still high. We are measuring
that cost, not hiding it behind the word "quick."

This is what onboarding needs to prove: the user can see which stage is
running, what the system actually learned, and where its view remains thin.
A neat page without those boundaries would only make an incomplete memory
look more certain than it is.

For the 1.8.9b11 preview, we kept the page and its sources separate from the
release image: the image shows only aggregate counts and the next command.
That is part of the same boundary. A useful first-run explanation should be
publicly inspectable without publishing anyone's correspondence. The deeper
project pass remains a measured limit: it completed, but took about 17 minutes
and reported more than a million input tokens. A beta should show that limit
beside the result so a newcomer can decide when to use the deeper route.
