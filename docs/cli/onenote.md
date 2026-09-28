# co onenote

Your OneNote notebooks from the terminal, and the same access for agents through
`OneNote()` (#1887). It needs `Notes.ReadWrite`, which `co auth microsoft`
requests since 1.8.9b20, or on a work or school account `Notes.ReadWrite.All`.
A personal Microsoft account (outlook.com) accepts only `Notes.ReadWrite`: a
sign-in from 1.8.9b19 asked for `.All` alone, so its token reads mail while
OneNote refuses it. Sign in again (#1910).

```bash
co onenote ls                                  # notebooks and their sections, with ids
co onenote pages "Lab notes"                   # pages in a section (name or id), newest first
co onenote read 0-8ab1…                        # one page as plain text
co onenote create "Lab notes" "Week 5" "Results went here."   # a new page; prints its id and link
echo "From stdin" | co onenote create "Lab notes" "Week 6"
```

- A section is found by id or by exact name. A name that matches several
  sections (the same section name in two notebooks) is refused, and every
  match is listed with its notebook and id.
- `read` converts the page's HTML to text. Images and attachments are named,
  not downloaded.
- `create` writes the text as paragraphs. It never changes an existing page.
- Class Notebooks and notebooks shared with you are included, because the
  scope is `.All`: everything you can open, not everything in the organisation.

## For agents

```python
from connectonion import Agent, OneNote

agent = Agent("notes", tools=[OneNote()])
agent.input("What did I write about the week 5 results?")
```

`OneNote()` exposes `list_notebooks`, `list_sections`, `list_pages`,
`read_page` and `create_page`. It uses the same credentials, refresh and
throttling retries as `Outlook()`.

## When it refuses

| Message | What to do |
|---------|------------|
| `Missing Microsoft Notes.ReadWrite scope` | `co auth microsoft` (sign in again; a sign-in from before 1.8.9 did not ask for OneNote) |
| `OneNote refused this sign-in (HTTP 401). A personal Microsoft account …` | `co auth microsoft` (a 1.8.9b19 sign-in on outlook.com lacked `Notes.ReadWrite`) |
| `No section named …` | `co onenote ls` for the exact names and ids |
| `Several sections are named …` | pass the section id instead |
