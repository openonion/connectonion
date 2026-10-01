# Three hundred and eighty files

On a fresh `co rem init` on the owner's Mac, one person page, Ody Zhou's, cost
2.77 million input tokens. What the gather collected for it fit in about 98
thousand characters. The announced estimate for the whole first run was 4.2
million tokens. This one page used two thirds of that.

The material was laid out the way #1850 designed it: an evidence directory the
agent searches, one file per mail, each with its source id in the heading. The
design was right about summarising. Digesting everything before writing a
word had cost the owner's own page 16 million tokens. It missed what a tool
call costs. An agent turn re-sends its whole context every time it opens a
file. Three months of mail with Ody was 380 files, and the model's own report
said it had narrowed its reading "instead of reading all 373 files". Each
file it did open sent the conversation so far again, so the cost grew with the
number of reads, not with the size of the mail.

So the files are now bigger and fewer. A month of one mailbox is one file,
split once it passes 40 thousand characters. Each mail keeps its `###
<source id>` heading, so a search hit still names one message to cite.
Attachments, coding sessions and chats keep their own files, because they are
read as wholes anyway. The instruction changed with the layout. It used to say
to read only the matching entries with sed. Now it says to read the files that
matter whole, newest first, because every tool call re-sends the turn.

We measured it on a copy of that fresh notebook, with Ody's page reset to its
stub and the same 90-day window, the same model and the same mail: 139 Outlook
and 138 Gmail messages. Input went from 2,775k tokens to 1,476k, output from
68k to 37k, and the whole run from 17m43s to 10m44s. Evidence went from 380
files to 119.

The page it wrote kept the core: co-founder, the signed term sheet and its
corrected name, the hostel proposal, the migration blocker, the LinkedIn
handoff. It was thinner on detail, and lost the term-sheet percentages and the
14 September migration fix. That is one run against one run, so it may be
variance, or it may be the cost of reading less. The next acceptance run will
tell. Halving the cost is real either way.
