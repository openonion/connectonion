# co onenote

Your OneNote notebooks from the terminal, and the same access for agents through
`OneNote()` (#1887). It needs `Notes.ReadWrite`, which `co auth microsoft`
requests since 1.8.9b20, or on a work or school account `Notes.ReadWrite.All`.
A personal Microsoft account (outlook.com) accepts only `Notes.ReadWrite`: a
sign-in from 1.8.9b19 asked for `.All` alone and may be refused by OneNote.
Sign in again if it keeps failing (#1910).

```bash
co onenote ls                                  # notebooks; sections numbered 1, 2, ...
co onenote pages 2                             # pages in section 2, numbered 1, 2, ...
co onenote read 1                              # read page 1 from that list
co onenote create 2 "Week 5" "Results went here."  # confirm the target section, then create
co onenote                                     # recent pages across all notebooks
co onenote pages                               # same, with --limit 20 by default
co onenote ls --ids                            # also print section IDs for scripts
co onenote pages 2 --ids                       # also print page IDs for scripts
```

- `ls` numbers sections across notebooks; `pages` numbers pages. Long Graph IDs
  are hidden by default and available with `--ids`. Numbers use the
  last list of the matching kind, saved for 15 minutes and bound to the selected
  Microsoft account. An empty list replaces the old numbers. Each list also
  prints a `Listing:` ID: use `--listing <id>` to pin those exact rows when
  another list has since been shown. Page and section IDs still work directly.
- A section can also be found by exact name or ID. Repeated section names are
  refused with every match; use a number from `ls` or the section ID.
- A page can also be read by exact title or ID. Repeated titles are refused
  with every matching ID; a number from `pages` avoids that ambiguity.
- Creating with a bare section number shows its notebook and section and asks
  for confirmation, defaulting to No. For a non-interactive script, use a
  section ID or a number together with `--listing <id>`.
- `read` converts the page's HTML to text. Images and attachments are named,
  not downloaded.
- `create` writes the text as paragraphs. It never changes an existing page.
- Graph can be slow. Calls wait up to 60 seconds; a timeout prints one recovery
  line instead of a Python traceback.
  If `create` times out, check the section before retrying: the page may exist.
- With a work or school account and the `.All` scope, Class Notebooks and
  notebooks shared with you are included. A personal account uses `Notes.ReadWrite`.

Names remain available when useful:

```bash
co onenote pages "Lab notes"
co onenote read "Week 5"
co onenote create "Lab notes" "Week 6" "From a script"
```

## For agents

```python
from connectonion import Agent, OneNote

agent = Agent("notes", tools=[OneNote()])
agent.input("What did I write about the week 5 results?")
```

`OneNote()` exposes `list_notebooks`, `list_sections`, `list_pages`,
`list_recent_pages`, `read_page`, `read_page_by_title` and `create_page`; the
terminal's row numbers do not change these agent methods. It uses the same
credentials, refresh and throttling retries as `Outlook()`.

## When it refuses

| Message | What to do |
|---------|------------|
| `Missing Microsoft Notes.ReadWrite scope` | `co auth microsoft` (sign in again; a sign-in from before 1.8.9 did not ask for OneNote) |
| `OneNote refused this sign-in (HTTP 401)` | Run `co auth microsoft` to obtain `Notes.ReadWrite` for a personal account. |
| `No section named …` | `co onenote ls` for the exact names and ids |
| `Several sections are named …` | pass the section id instead |
