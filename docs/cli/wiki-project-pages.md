# Project pages from your own messages (#1943, stage 2)

The first run should leave you with something true about your projects, not a
list of empty frames. The best record of what a project is and where it stands
is what you told your coding agents while working on it. This stage reads only
that — the messages **you** typed in your local Codex and Claude Code
sessions — and writes each project's page from it, most recently active
projects first.

It is two steps, and only the second one uses a model.

```text
  your Codex / Claude Code sessions (read only)
                 │  1. script, no model: your messages only, per project folder
                 ▼
  .state/projects/<page>/messages.md      (0600, owner-only)
                 │  2. one model call per page, recent projects first
                 ▼
  projects/<page>.md                      (validated, then saved)
```

## Commands

```sh
co wiki projects                      # step 1 + the order and the cost; no model
co wiki projects write                # step 2 for the next 5 pages, recent first
co wiki projects write --limit 1      # just the most recent project
co wiki projects write --recent-days 7 --limit 0   # every project active this week
```

`co wiki projects` refreshes the material — filing messages typed in a
workspace by the repository they worked in, and making pages for folders active
in the last 14 days that have none — and says how many of each. It then prints,
for each page with something new, when it was last active, how many of your messages are new, and
whether it is a first write or an update. It ends with the cost of writing them:
one model call per page and the characters (about four to a token) each call
will carry. Nothing is spent.

`co wiki projects write` refreshes the material, states the same cost for the
pages it is about to write, then writes them one after another with the
configured runner (`co wiki config`), the same way `co wiki investigate` runs a
page. Every run is recorded in `co wiki logs` and counts toward investigation's
weekly Codex budget; a run stops starting pages when that budget or the floor
kept for your own work is reached.

## Step 1: the material (a script)

For every enabled Codex and Claude Code source, each session file is read line
by line. Only messages you typed are kept, using the same parser that
`co wiki sync` uses: the assistant's replies, tool output, injected harness
blocks (`<environment_context>`, skill bodies, subagent prompts) and the
notebook's own model runs are skipped. A message is filed under the project
page whose `Paths` contain the folder the session ran in (the deepest match
wins, so a worktree listed on a page counts for that page). Folders
`co wiki scan` would never map — temporary directories, the notebook's own task
copies — are skipped with the same rule (`project_exclusion`). A message typed
in a multi-repository workspace container is not skipped: it is filed under the
repository its session actually worked in (below). A folder with your messages
but no page gets one if it was active in the last 14 days (below).

### Sessions typed in a workspace

A workspace container is a folder that holds several repositories and says so in
its agent instructions (`CLAUDE.md` or `AGENTS.md`, no `.git` of its own, two or
more child repositories) — the owner's `~/projects`. The map never makes it a
page, because it is not one project, and `project_exclusion` still says so. But a
session started there works in one of its repositories, and the session file
says which: every tool call names the paths it touched. So a message typed in a
workspace is filed by the evidence inside its own session, read by the same
script, no model:

| Evidence | Codex | Claude Code |
|---|---|---|
| A change of working folder | `turn_context.cwd` | the `cwd` on each tool call's row, which follows `cd` |
| Files read, edited or written | paths in the tool call (`exec`, `apply_patch`, `shell`) | `file_path` / `path` / `notebook_path` of `Read`, `Edit`, `Write`, `Grep`, `Glob` |
| Commands | absolute paths, `cd DIR`, `git -C DIR`, `workdir` | absolute paths, `cd DIR`, `git -C DIR` in `Bash` / `Monitor` |

Only the calls the agent made are read, never their output, and never the text an
edit wrote. A relative `cd` or `git -C` is resolved against the folder the call
ran in. Each path is taken to the **deepest existing project folder** that holds
it inside the workspace: a folder listed on a project page, or a folder with its
own `.git` (a repository or a linked worktree), whichever is deeper. A path in
the workspace itself (its `CLAUDE.md`), outside it, or in a folder
`project_exclusion` skips is no evidence. One tool call counts once per project
folder it touches, however often it names it.

- **Per message, where the evidence is per turn.** A turn is what the agent did
  between one typed message and the next. A message goes to the project folder
  its own turn touched most, so a session that moved from one repository to
  another is split message by message.
- **Otherwise the session's.** A message whose turn touched no project (a
  question answered without tools) goes to the folder the whole session touched
  most.
- **Otherwise it stays out.** A session that pointed at no repository at all is
  counted as typed in a multi-repository workspace container, as before, and
  reaches no page.

A tie goes to the folder touched first. The message keeps where it was typed
(`typed_in` in `messages.jsonl`), and its `cwd` becomes the project folder, so
the page it lands on is chosen exactly as for any other message.
`co wiki projects` says how many messages were filed this way, and `--json`
carries it as `workspace.attributed`.

### Folders with messages and no page

A folder with your messages and no project page — a repository a workspace
session worked in, or a folder the map has not seen since its last run — gets a
page when its newest message is within the last 14 days (`--recent-days`). The
page is made by the map's own code (`map.file_project`): the same stub, the same
record name, and a worktree joins its repository's page by origin, exactly as
`co wiki init` would have made it. It starts `mapped`, and is written from your
messages like any other. An older folder is listed, not given a page:

```text
3 more folders with messages and no page; not created (older than 14 days)
```

A page made on a later, incremental run holds that run's messages; run
`co wiki projects --full` to file its older ones too.

Each project page gets a private folder:

| File | Holds |
|---|---|
| `.state/projects/<page>/messages.jsonl` | Every kept message: time, tool, source id, text. The exact copy |
| `.state/projects/<page>/messages.md` | The same, as plain text to read: one `###` heading per message |
| `.state/projects/<page>/state.json` | Paths, message count, first and last activity, and `written_through`: the newest message the page was written from |
| `.state/projects/index.json` | When the material was last extracted, the pages it made, how many workspace messages it attributed, and folders with messages but no page |

Directories are `0700` and files `0600`, like the rest of `.state/`. Text in the
shape of a key or token (`sk-…`, `AKIA…`, `ghp_…`, private key blocks, JWTs) is
replaced with `[secret-shaped text removed by co wiki]` before anything is
written, so it never reaches the disk copy, the model, or the page. A password
in plain words is not a shape; the skill tells the model never to copy one.

**Only what is new.** The first extraction reads the last 180 days (the most a
coding source may read). Every later one reads only session files changed since
the previous extraction, and only messages after it (with a one-hour overlap for
a line that was still being written; a message is identified by
`tool:session:offset`, so the overlap never duplicates one). `--full` reads the
whole window again.

### Caps, and why

Measured on the owner's machine on 2026-09-30, read-only, counts only: 1,567
session files (4.4 GB) changed in 180 days were read in 7 seconds. They held
1,359 typed messages; 614 of those were typed in folders the map excludes (590
in the `~/projects` workspace container, 24 in temporary directories). The other
745 messages, 203 KB in all, fell in 43 project folders, 21 of them active in the
last 14 days. Per folder: median 0.9 KB, 90th percentile 10 KB, largest 38.7 KB
(144 messages). The largest single message was 6.9 KB.

| Cap | Value | Why |
|---|---|---|
| One message | 4,000 characters | The existing session parser's cap: nobody types more; a longer one is a pasted log, and its head says what it was |
| Stored per page | 400,000 characters, newest kept | Ten times the largest project measured; bounds the disk copy of a very busy year |
| Sent in one write | 60,000 characters, newest kept | Fits the largest measured project whole, and with the two skills and the page stays under the runner's 100,000-byte inline prompt, so the model is handed everything rather than told to go read files. Anything older that does not fit is named in the material's coverage note |

## Step 2: the page (a model)

One call per page, through the configured runner (`co ai --harness codex` by
default), in the same sandbox as investigation: it may write only its candidate
file. The call is given two skills — `wiki-project-sessions` (how to read your
messages) and `wiki-page-project` (the page's shape) — and two inputs: the page
as it stands, and your messages for that project. Those are the whole input.

- **First write**: all your messages for the project (the newest 60,000
  characters of them).
- **Update**: the page as it stands and only the messages after
  `written_through`. A project with nothing new is not written again.

The page it writes passes the same review as an investigated page: canonical
sections, every citation pointing at a supplied message, mapped `Sessions` /
`First seen` / `Last seen` kept. A refused page is kept beside its task with the
reason, and `written_through` does not move, so the next run tries again. An
accepted page's status line gains `written <date> (own messages: codex,
claude-code)`.

Your messages say what you wanted, decided and saw; they do not prove a build
passed or a site went live. The skill writes a request as a request and a
reported result as reported by you, and leaves what the messages do not say
`Unknown`. Reading the repository itself stays with `co wiki investigate`.

### Measured

One real run on 2026-09-30, against a temporary notebook holding one project
page (a folder with 138 of the owner's messages over 180 days, last active the
day before), runner Codex with `gpt-6-luna`:

| | |
|---|---|
| Step 1 (no model), first extraction | 14 s for the command, 1,571 session files; 747 messages kept, 614 skipped as typed in excluded folders |
| Step 1 again (only what is new) | 7 s; 8 new messages from 17 changed files |
| Stated cost | 1 call carrying 47,187 characters (~11.8k tokens) |
| The call | 65 s; 86,710 input tokens (52,736 cached), 4,831 output; the Codex week read 22% before and after |
| The page | Accepted by review: all 15 sections, 27 cited sources, 5 lines left `Unknown` |
| Before that | One attempt failed in 1 s: the prompt opened with `/wiki-project-sessions`, a slash command `co ai` could not resolve. It now opens with the `<co_wiki_task>` tag, which is also what keeps the run's own prompt out of the next extraction |

The stated cost is what one prompt carries. The runner is an agent that re-sends
its context each turn, so billed input was about seven times the prompt; the
cost line says so rather than presenting the prompt as the bill.

## Order

Pages active in the last 14 days (`--recent-days`) come first, most recent
first; older ones follow, most recent first, in portions of `--limit` (default
5). The same ordering is exposed as `connectonion.wiki.project_pages.queue()`,
so the first-run flow and the daily round can call it.

The daily round (a later stage) is designed around this material: of four runs a
day, one investigates unfinished pages; the other three call `extract()` (only
new session lines) and `write_pages()` (only projects with new messages, each
given only its new messages).
