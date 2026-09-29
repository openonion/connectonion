# Six things a real notebook found

The 1.9.0a1 preview was tested on a copy of the owner's notebook before
anyone else ran it: 370 people, 138 organisations, three paid investigations
and one maintenance run. The new evidence path worked: input tokens came down
three to eight times against the same subjects a week earlier. Six of the ten
problems the run found were small enough to fix the same morning, and each
one had been hiding behind something that looked like it was working.

**A citation in a search query.** Tamara's page had been investigated before,
so its handle line read `Tamara Berryman; tamara.berryman@unsw.edu.au [2]`.
The next investigation read that line back as a handle, `[2]` and all.
Because the text contained an `@`, it went to Gmail as an address, and Gmail
matched 677 unrelated mails. The run took twenty minutes and read ten million
characters, and the page came back with nothing new. A handle is now read
without its citation and split on semicolons. Only a whole address goes to the
server.

**A rule the model obeyed too well.** The investigate Skill said to read the
CLI reference first. Every run did, as its first action: a 12.6k-character
file inside a turn we had just cut to 14.8k. It is now read only before a
`co` command, which an offline run never makes.

**Private copies nobody deleted.** Each run's task folder kept the material
it had been handed. Across 98 folders that was 75 MB of the owner's mail. A
finished task now keeps its record, its candidate page and the Skill text,
and nothing else.

**A copy that claimed a schedule.** The copied notebook said "Running in
background", and `doctor` said "ok schedule". The job it pointed to runs the
original. Status now checks that the installed job runs this notebook.

Two smaller ones: every stage records its instruction size, not just
investigate, and a page's status line no longer lists "evidence" as a source.
Three more fixes are in their own pull requests, and one, pages that grow
with every maintenance pass, needs a decision about how pages should age.
