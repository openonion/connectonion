# Notes with nowhere to go

One sync on the owner's notebook read a week of coding sessions and wrote
eleven project notes. Ten of them were about the notebook itself: the rename
to co rem, the evidence files, the new prompts. The run changed one page, a
thousand-character page for another project, and reported "Unrecognised:
None". The ten notes had nowhere to go, and nothing said so.

The notes existed: they were on disk in the run's extract file. They were lost
at the step that decides which pages a batch should touch. That step looks at
the raw material, not at the notes. It picks pages two ways: a session ran
inside a folder a project page lists, or a page's title appears in the text.
These sessions had been typed in the workspace root, `~/projects`, which is
the parent of every project and belongs to none. The text said "co rem" and
"the Wiki". No page was titled either. So the batch found no page for the work
the owner had spent the week on.

The notes knew where they belonged. The extraction writes each one under
`## Projects` with the project's name in bold, because a person reading them
would want to know. We were asking the raw text a question the model had
already answered in the notes.

Now, after extraction, sync reads those names and matches them to project
pages by title or by the name of a folder the page lists. A page found that
way joins the batch while the day still has attempts left. A name that no
page answers to is written into the run record and the run's report, so it
is visible instead of dropped.

The same test found a smaller version of the same problem. A project page
written by `co rem projects write` gets its status line stamped `written
<date>`. The next investigation counted only `investigated`, so it read 150
days again, 1.58 million tokens' worth, a few hours after the page had been
written from those same days. A written page now starts the next window too.
