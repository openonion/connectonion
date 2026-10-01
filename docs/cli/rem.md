# co rem — current branch contract

Updated 2026-09-24. co rem ships in the opt-in 1.8.8 previews and becomes
long-term supported in 1.9.0 (#1664 names it first). The command surface and
every `--help` page are the agreed design in #1656; the pages themselves live
in `connectonion/cli/commands/rem_help.md` and a test holds them to the code.
Old command names (`unfinished`, `people`, `daily`, `subscribe`, `subscriptions`,
`unsubscribe`, `route`, `usage`) still work until 1.9.0 and print their new name.

See the [2026-09-17 progress review](rem-progress.md) for the feature inventory,
current CI blockers and remaining work.

## Coming from co wiki (1.8.8–1.8.9)

1.9.0 renames the feature `co rem` (#1932). Nothing needs doing by hand:

- The first `co rem` moves `~/.co/wiki` to `~/.co/rem` and says so in one line.
  If both folders exist it refuses, names both, and merges nothing. An explicit
  `--root` is used as given. A move that fails leaves the old folder whole.
- A daily schedule that `co wiki start` installed is replaced by one that runs
  `co rem sync`, the next time `co rem` runs for that notebook.
- `co wiki …` runs nothing in 1.9.x: it exits 2 with `co wiki is now co rem.`
  and one `Next: co rem …` line with the same arguments. It is removed in 1.10.
- `CO_WIKI_PROGRAM` is still read when `CO_REM_PROGRAM` is not set, with a
  one-line notice. `pip install 'connectonion[wiki]'` still installs the
  spreadsheet extra, now called `rem`.

## Start here

```bash
co rem init                 # Build the map (no model), show your own page, then write it (one model turn)
co rem open                 # Read your page
co rem start                # Keep it current: approve sources, turn on the daily round
```

The first run is one command (#1943). `init` is a script: it maps 90 days of
mail and your local Codex / Claude Code sessions, saves the private mail
material, and prints your own page's facts — who you write to most, how much
mail, which projects you have been coding in — with the page's path, within the
first minutes. Then, in a terminal, it writes your own page by itself: the whole
`investigate me`, from everything you sent and your coding sessions of the last
30 days (or `--days`), one model turn over evidence files, about 15 minutes.
It writes a quick first pass of your page in about 2 minutes, then the whole
page alongside everything else. Next
come everyone in the people queue, every project with session messages and the
organisations you correspond with, 12 pages at a time; on the owner's real
notebook (1,880 mails, 1,300 coding sessions) that wrote 198 of 242 pages in
about 25 minutes. Before it spends anything it says which runner and model, that
it runs on your own plan, and roughly how long. The whole first run stops
starting pages once it has used 60 points of the Codex week, or at the weekly
budget or floor; pages already in flight finish. Ctrl-C stops it and keeps the map
and every page written; `co rem investigate people` writes more people. It skips that step, with a one-line reason, when
the runner is not installed or not signed in (checked before the map starts,
without a model), when no mailbox gave an address of yours, when your page was
already written, or when there is no terminal (scripts and `--json`) unless
`--investigate` is given. `--no-investigate` builds the map only.

After your page, by the same rules, init writes the project pages of projects
active in the last 14 days, from the messages you typed in their Codex and Claude
Code sessions (the `co rem projects write` pass, #1947). It states the cost first
— one call per project, about a minute and ~90k billed input tokens each, plus
the Codex week's meter — prints one line per page, and stops starting pages at
the weekly investigation budget or the floor kept for your own work. Older
projects wait for `co rem projects write`.

Progress is one line per stage (updated in place in a terminal); every step is
kept in `.state/init-progress.log`. Addresses that look like yours (you wrote,
nobody replied) are listed on one line with one command that confirms the ones
you keep: `co rem init --mine a@example.org,b@example.org`. Mailboxes init read
are subscribed, so `co rem start`'s summary lists them as sources to read; start
still asks before anything is read in the background.

To fill other pages, `co rem investigate` lists what is left, by category, and
runs no model. Copy the `Next:` command printed by `investigate` to investigate one existing
page. You can also supply an exact title or email when it identifies one page,
for example `co rem investigate 'Ody'` if that person exists in your notebook.
Ambiguous names list the matching paths and do not start a model. Example page
names in old help text, such as `people/emma.md`, are not built-in records.
`--help` displays help and exits, even when you also supply a page name.

```bash
co rem investigate          # What is left to investigate, by category; no model
co rem investigate me --quick --days 5  # Bounded first pass; disclose uncovered sources
co rem open                 # Open a fresh snapshot of the notebook in your browser
co rem sync --dry-run       # Inspect pending metadata, without running a model
co rem sync                 # One update: new material, then at most one unfinished page
co rem logs                 # Inspect results, partial coverage and failures
```

Normal output uses readable labels and plain page paths. Empty lists explain
what is missing; unknown usage remains **Unknown**, never zero. Results end
with a copyable `Next:` command, including the selected root and shell quoting.
Use `co rem --help` as the workflow guide: it gives task selection,
observed inputs, expected results, source/quality checks and recovery before
the command inventory. `init --help`, `investigate --help` and `sync --help`
explain their full workflow as well as options. The overview and group help
share one implementation, so human and agent guidance cannot drift separately. Root and JSON flags belong **before** the subcommand:

```bash
co rem --root '/path/to/my co rem' investigate
co rem --root '/path/to/my co rem' --json status
```

Explicit `--json` retains the `ok`, `data`, and `next` envelope for scripts.
No-argument `--json` continues to return status, without the human guide.
Piping human output does not hide the next step. Grouped help covers:

| Task | Commands |
|---|---|
| Map and investigate | `init`, `investigate`, `map-skills`, `scan`, `stub` |
| Browse | `open`, `list`, `show`, `search`, `status` |
| Update and review | `sync`, `capture`, `reflect`, `reflections`, `propose`, `review`, `abstract` |
| Sources and background | `sources`, `sources add`, `sources remove`, `start`, `stop` |
| Settings and diagnostics | `config`, `config set`, `logs`, `doctor` |

`start` explicitly authorizes collection and installs background maintenance
plus at most one unfinished-page investigation per local day when the day's
call budget allows;
`init` does neither. A mapped page is not an investigated or quality-approved page.
For an initial trial, `co rem init --days 5` investigates your page over the same
five-day window. `investigate me --quick` is the older bounded pass: it samples
recent evidence, takes one synthesis turn, and marks its coverage as partial.
init no longer uses it, since #1850's evidence files let one turn search
everything you sent.

## Installed-skill skeletons at initialization

`co rem init` deterministically builds People, Organizations, Projects and Skills pages from
their canonical templates and available source metadata before any model
investigation. Unknown fields remain explicit; investigation is a separate step.
See the [initialization interaction contract](rem-init-contract.md).

Its coverage lines keep the four source states apart, because each one needs a
different next command:

```text
gmail: metadata only, 90 days; a seven-day window at the 200-message listing cap is split until every message in it is listed; 42 correspondents
outlook: not connected; not searched. Connect it with co auth microsoft
codex: /home/you/.codex/sessions — scanned; no sessions in this window
claude-code: /home/you/.claude/projects — disabled; not scanned
```

A mailbox that was read and held nobody, one nobody has connected, one the user
unsubscribed, and one that is connected but would not open are four different
answers; so are a session directory that is missing, one switched off, and one
scanned that had nothing inside the window.

Where init can see that an address is probably the user's own — mail goes to it
repeatedly and nothing ever comes back — it says so and prints the exact
`init --mine <address>` that confirms it. It never merges on the guess: an
assistant and a family member look the same from the headers.
The map can also be run independently:

```bash
co rem --root /private/path/to/rem map-skills
co rem --root /private/path/to/rem map-skills --skills-dir /known/project/.co/skills
```

The generated `skills/catalog/index.md` links to **one page per skill name**
(#1974). A skill installed three times — in `~/.claude/skills`, `~/.codex/skills`
and `~/.agents/skills` — is one page, not three. The page links to the source
file instead of pasting it, and keeps the frontmatter facts short: the name, the
description, the allowed tools. Its `Source` section, which the map owns and
rewrites on every run, lists each copy:

```text
## Source
- File: /home/you/.claude/skills/ship-feature/SKILL.md
- Discovery: claude-user
- Allowed tools: Bash, Read
- Content: sha256 3f2a9c1e04b7; 3 installed copies
- Also installed at: /home/you/.codex/skills/ship-feature/SKILL.md (identical)
- Also installed at: /home/you/.agents/skills/ship-feature/SKILL.md (differs: sha256 77b0d2e41f9a)
- Status: mapped from metadata; behavior not verified
```

Copies are compared by content hash, so a copy that has drifted says so. A copy
in a temporary or package location — a git worktree (`.claude/worktrees/`,
`.worktree/`, `.worktrees/`, `.codex/worktrees/`), `site-packages`, a plugin
cache — never becomes the `File` of a page and never
makes a page of its own; it is listed as `Also installed at` on the page of a
copy that lives somewhere real. A name found only in such places is listed in
the index under "Only in temporary or package locations", without a page.

`Usage history` opens with what your own coding sessions say, counted by a
script with no model: how many times the skill was invoked and when last.

```text
- Invoked 14 times in your coding sessions in the last 180 days, last on 2026-09-28 (Claude Code 9, Codex 5). ...
```

Claude Code counts a `Skill` tool call and a `/skill-name` command; Codex counts
a `$skill-name` in a message you typed (read as `sync` reads it, Codex Desktop
included) and a tool call that reads the skill's
`SKILL.md`, once per turn. co rem's own runs are not counted. An invocation is
not a completed run: `Current status` and `Performance` still wait for run
evidence. Counts are cached per session file under `.state/skill-usage.json`,
so a rerun reads only what changed.

Rerunning the map (`init`, `sync`'s map, or `map-skills`) moves an older
notebook to this shape. Pages made one per copy are merged into the name's page:
a page with written content keeps it (sections are merged line by line, citations
renumbered), the pasted `SKILL.md` snapshot is removed, and the old page is
moved to `.state/archived/` — never deleted. Its record becomes an **alias**
(`.state/aliases.json`): links to it in other pages are rewritten, and a command
given the old name opens the merged page. A page whose only source was a
temporary copy and that holds nothing but map output is archived the same way.
Original `SKILL.md` files are never changed or run, and `skills/approved/`
remains write-protected.

Defaults cover the co/Claude skill search roots, conventional agent/Codex skill
roots, and co ai's bundled default allowlist. This is a shallow inventory, not
an exhaustive plugin-cache or remote-catalog scan. Repeat `--skills-dir` for
explicit roots; supplying it replaces defaults for that scan. Coverage and
unreadable files are reported in the index and command result.

The [co rem CLI reference](../../connectonion/useful_skills/rem-init/CLI.md) explains
mail IDs, browser tabs, source/working/output directories and failure recovery.

## One execution path

```text
User / scheduler
      |
      v
co rem init / investigate / sync / abstract
      |
      | stage Skill + source Skill + page shape + material paths
      v
co ai --json --harness <codex | claude-code | ours> /rem-<stage>
      |
      +-- Codex tool       --> Codex subscription
      +-- Claude Code tool --> Claude Code subscription
      +-- COAI agent       --> configured LLM provider (including Ollama)
      |
      v
Markdown pages + reported usage + observed file changes
```

COAI already delegates before creating its own LLM loop. Selecting Codex
therefore does not spend a COAI model turn deciding to delegate. All co rem
stages, including extraction and maintenance, use that same command.

co rem's former app-server subclass, dynamic rem_* tools, isolated Codex HOME,
auth-file copying, native version/config checks and direct native extraction
path have been removed. The shared COAI native adapters remain: their job is
to speak Codex or Claude Code's protocol once for all callers.

co rem retains source importers, bounded digest batches, page templates,
identity roster, progress, sync locking/accounting, OS scheduling and the
reader. A shell can call the public CLI; rewriting these data operations as a
second shell implementation would duplicate behavior.

## Commands

Group options precede the command: `co rem --root /path/to/rem --json list`.
Every command returns a next command, including in JSON and through a pipe.

| Command | Behavior |
|---|---|
| `co rem init` | Discover accounts and local sources, build People/Organizations/Projects/Skills pages with no model, print your own page's facts, then (in a terminal) write your own page with one model turn. `--no-investigate` stops after the map. |
| `co rem scan people --days 150 --min-mails 1` | Enumerate correspondent signals from Gmail/Outlook; no model. Repeat `--mine <address>` for own addresses. |
| `co rem scan orgs --days 180 --min-people 2` | List work domains that two or more people write from — where an organisation page earns its place. No model. |
| `co rem scan projects --days 150` | Enumerate session working directories and local Git repository identities; no model. |
| `co rem stub person "Alice" --email alice@example.org --handle 艾丽丝` | Create the canonical person skeleton if absent. |
| `co rem stub org "UNSW" --domain unsw.edu.au --person people/vern-chan.md` | Create an organisation skeleton; `People here` holds links, not copies. |
| `co rem stub project "Aurora" --path /path/to/repo` | Create a project skeleton. |
| `co rem list people --aliases` | Existing identity roster: page, title, aliases, addresses, relationship summary. |
| `co rem list people --review` | Pages held for review: titled by an address the owner never wrote to, or only ever wrote to. |
| `co rem investigate people/alice.md` | Read the existing page, gather sources, digest oversized material, fill that same page through the Skill. |
| `co rem investigate` | What is left to investigate, by category, most useful first. No model. |
| `co rem investigate people --limit 3` | Investigate the next three people, the last 14 days' correspondents first (`--recent-days`): a person investigated before reads only the mail since then ([details](rem-people-pages.md)). `--list` prints the order and the cost and runs nothing. `projects`, `orgs`, `skills` take unfinished pages, most mail or sessions first. |
| `co rem investigate me` | Fill your own page from what you sent and your coding sessions of the last 30 days. |
| `co rem abstract` | Run rem-abstract over existing notebook evidence. |
| `co rem start` | Confirm source access, run first bounded sync, install macOS background schedule. Asks again whenever anything its summary shows (sources, runner, model, permissions, schedule, limits) changed since the last approval. A start after `stop` resumes the schedule without a batch; `co rem sync` runs one. |
| `co rem start --yes` | Explicit noninteractive consent for start. |
| `co rem stop` | Remove that notebook's background job; preserve pages and progress. |
| `co rem sync` | The whole update: one batch of new material; then the day's first run investigates unfinished pages, most recent first, and every later run updates only the people and projects with something new. What the schedule runs (`sync --scheduled`). |
| `co rem sync --source codex --dry-run` | Pending metadata only; no model or source body reads. |
| `co rem sources add codex --project /path/to/repo --since 30d` | Save a scoped source choice. |
| `co rem sources add whatsapp --chat <id>` | Read one WhatsApp chat (group or person) from the files `co whatsapp listen` keeps; ids from `co whatsapp chats`. Repeat per chat; the next `co rem start` shows it and asks before anything is read. `co rem sources remove whatsapp --chat <id>` stops one chat. |
| `co rem sources remove codex` | Disable that source. |
| `co rem list people` / `show people/alice.md` / `search Alice` | Inspect Markdown without model calls. |
| `co rem status` / `sources` / `config` / `logs` / `logs --usage` / `doctor` | Inspect configuration, progress, diagnostics and reported usage. |
| `co rem open` | Render a fresh self-contained HTML snapshot to a temporary file and open it. Works offline; prints the file path and a `file://` link. |
| `co rem open --live` | Open the live view in O Chat, read from your `co ai` Host over OIP. Checks first that the Host is online; if it is not, says so (start it with `co ai`) and opens the snapshot instead. Default notebook only. |
| `co rem open --no-launch` | Print the page without opening the browser. |

Until 1.8.9 the default opened `https://chat.openonion.ai/<address>/wiki` before
O Chat served that route, so the page never loaded (#1828). O Chat serves it
since openonion/oo-chat#246; opening locally stays the default because it works
offline and needs no Host, and the live view is asked for with `--live`. The
route and both switches live in `connectonion/rem/reader.py` (`LIVE_WIKI_URL`,
`LIVE_WIKI_SERVED`, `LIVE_IS_DEFAULT`). `--local` is still accepted and always
means the snapshot. If the live view says co rem is not yours, add the
browser's address as an admin of the Host: `co trust admin add <address>`.

The page reads each record for what it knows (#1836). A page carries one of
three tags: **Mapped** (an outline from your sources; its status line still says
"not investigated yet"), **Some findings** (written content, no investigation
pass yet) and **Investigated**. "Unknown" lines and placeholders are not shown;
the headings still empty are named once at the foot of the page with the
`co rem investigate '<page>'` command that fills them. Lists put pages with
findings first, then newest last contact. The Markdown file is unchanged, and
**Copy Markdown** at the foot copies it as written, unknowns included.

`init` is the foreground Skill workflow. `start` remains the explicit
background lifecycle command; initialization does not install a schedule.
Map is a stage inside rem-init, not a separate model runner.

Map reads known information before leaving basic fields unknown. It uses the
single person-page definition; investigation reads that same existing page,
keeps supported facts and fills gaps. The owner is investigated first.
Automated notices are signals for the Skill to classify, not an automatic
rule to discard companies or event opportunities.

## Choose a harness

```bash
co rem config set runner codex model gpt-5.6-luna
co rem config set runner claude-code model default
co rem config set runner coai model co/gemini-3.8-flash
co rem config set runner coai model ollama/qwen3
```

A model name must be available in the selected provider/account. `default`
omits the model flag. Changing runner without a model chooses that harness's
default. Old coai configs which retained the unused Codex default migrate to
their previous effective behavior (COAI's default). No credential belongs in
co rem configuration.

### The job's shape: agent or summary tier

Not every model can drive tools, and model names change under us, so the
shape of an investigation is measured rather than read off the name (#1847).
Changing `model` or `runner` runs a capability check: one investigation of a
built-in fixture page (two mails, in a throwaway notebook; none of your data)
through the configured runner, graded by code — the page must state the
fixture's fact and cite a fixture message. The result is recorded in
`.state/tier.json` with the runner, model and time it was checked for.

| Tier | Who gathers | Who writes the page |
|---|---|---|
| `agent` | co rem's code gathers; the harness reads the material with its file tools | The model writes the page file itself, as the investigate Skill says |
| `summary` | co rem's code gathers everything, including a project's files, and hands it all over inline (digested first if it does not fit) | The model replies with the page, one page per call; the reply becomes the candidate |

The agent tier is tried first; a model that fails it but fills the page by
reply is the summary tier; a model that does neither is not recorded and the
command fails with a `Next:` line. `co rem config` shows the tier in force.
A notebook never checked, or checked for another runner or model, runs as the
agent tier (the behaviour before the check existed) and `co rem config`
says so and names the command that checks it. `--no-check` saves a new model
without checking it.

```bash
co rem config set model gpt-6-luna      # saves, checks, records the tier
co rem config                           # Tier: in force, checked, when
```

Equivalent direct CLI delegation, useful in a shell script:

```bash
co ai --json --harness codex --model gpt-5.6-luna \
  "/rem-investigate Update /path/to/rem/people/alice.md; read its current content first."
```

The direct Skill call does not run co rem's deterministic source collection or
advance its sync cursor. Use `co rem investigate` for that orchestration.
COAI expands the Skill name and supplies its installed directory.

Every co rem model turn starts from the fixed `.state/tasks/` workspace inside
the selected co rem root (`~/.co/rem` by default). Codex therefore groups
those turns under one workspace in its history. Inputs, review results and
disposable page copies live in per-run subdirectories there;
the runner validates a candidate before promoting it to the notebook.

Every co rem stage reads text other people wrote -- mail bodies and PDF, DOCX
and XLSX attachments -- and the daily job `co rem start` installs runs with
nobody watching. So every stage, scheduled or started by hand, runs confined:

| Runner | Flags co rem passes to `co ai` | What the model can do |
|---|---|---|
| `codex` | `--sandbox workspace-write` | Read files; write only inside `.state/tasks/` and TMPDIR; no network |
| `claude-code` | `--permission-mode acceptEdits` | Read and write inside `.state/tasks/`; commands, web fetch/search and reads elsewhere are denied, since nobody is there to approve them |

`co rem start` shows the row for the configured runner in its consent
summary, as `model_permissions`, before you approve the schedule, and
`model_receives` names whose login the model is called through (Codex or
Claude Code). Change the runner later and the next `start` shows the
summary again.

Model turns and the launchd job both run the installation that is running
`co rem` -- `<its python> -m connectonion.cli.main` -- not the first `co` on
PATH. Starting from a non-activated venv with an older `co` in `~/.local/bin`
used to install a job, and route every model turn, through the older one.

co rem's own code fetches the mail and attachments before the model starts, so
the model needs nothing more than to read that material and write the page
copy it is given. The cost is the web: investigation no longer looks up a
role or a switchboard number with `co browser`, and says so in the page's
`Uncertainties`. Before 1.8.8 investigation ran Codex with
`danger-full-access` and Claude with `bypassPermissions`, which gave anyone
who could email the user an unattended agent with a shell, the network and
the user's mailbox; a line in the prompt was the only defence.

co rem removes an ambient `ANTHROPIC_API_KEY` from Claude's subprocess
environment so the run uses the selected account's subscription rather than
silently billing the API. Skills govern what the task should do; they are not
OS permission enforcement.
The removed scoped rem_* tools are no longer a filesystem guarantee.

## Source coverage and output

Gmail/Outlook programmatic collection searches the requested date windows.
Sync lists each weekly window 200 messages at a time and splits any window
that comes back full until every half fits, so a busy week is read whole; a
single second holding more than 200 messages stops the scan with an error
rather than skipping them. Investigating a person on a client without a
server-side search still reads at most 200 messages per weekly window.
Coding investigation now walks successive batches until the cursor stops,
rather than stopping at 40 messages. It searches aliases and project paths;
an owner identified by mailbox address receives their own typed session
messages. Injected Skill prompts are not reingested as user experience.
The importer still labels oversized pasted session text as truncated.

What counts as a message you typed to Codex (#1978). Codex Desktop puts every
message in the user slot under a metadata block, typed or injected, and says
in `content_item_kinds` what each part is. A message whose parts are all
`user.*` (text, an image) is yours and is read; one that names anything else
(`agents_md.instructions`, `environments.environment_context`,
`plugins.recommendations`, `goal.internal_context`, a selected skill), or no
kinds at all, is the client talking and is skipped and counted. A message that
opens with a harness tag is still skipped, except the in-app browser context
Desktop puts in front of what you typed: that block is dropped and your words
are kept. Two kinds of thread are not read as yours: a subagent's (the
approval reviewer, a spawned worker), whose user slot the agent wrote; and the
history of a Claude Code session imported into Desktop, which co rem already
reads from Claude Code itself. What you type after an import is read. The Codex
CLI's plain three-key message is read as before. `$skill-name` counts in a
skill page's Usage history use the same reading.

PDF, DOCX, XLSX, PPTX (including tables/notes), plain text, HTML and ICS
attachments are read; XLSX needs `pip install 'connectonion[rem]'`, and
without it a spreadsheet is named as unread with that command. Investigation passes full extracted text to chronological
digest chunks instead of dropping a long attachment's tail. Unreadable
formats/errors remain visible. The Skill supplements from the account's
`co email` service, known documents and public sites, and reports what it
could not search. Own-mail sent history currently has no paginated CLI;
Jira discovery/auth is not connected to this co rem entry point yet.

Each task supplies material and composed instructions as files, avoiding
OS argv size limits. File changes are observed on disk, including deletions
and partial changes on failure; a success sentence is not a file-change count.
Extraction returns its written notes file, not a commentary/status reply.
Nonzero exits, missing/malformed envelopes, provider errors and timeouts fail
the task. Investigation is not marked finished on a failed execution.

co rem forwards its delegated deadline as `co ai --timeout SECONDS` and gives
the outer process 15 seconds to exit afterward. The common native adapter
therefore closes its delegate before co rem process timeout is reached.

## Scheduling and accounting

launchd invokes the resolved `co rem --root ... sync --scheduled` CLI every
five minutes, with PATH entries for co and installed delegates. Saved local
time slots determine whether a batch is due. Repeated start reloads one job;
missed slots coalesce into one catch-up. No permanent co rem daemon is added.

Each notebook root is its own job, `ai.openonion.co-rem.<hash of the root>`,
the default `~/.co/rem` included, so `co rem start`/`stop` under another
`HOME` never touches your real job. A job installed before 1.8.8b12 under
the bare label `ai.openonion.co-rem` is still found: `stop` removes it and
`start` replaces it, but only when its own `--root` is this notebook.

Sync retains its source cursor on failure. Two-stage batches reserve two
attempts and cannot start with only one remaining; extraction usage survives
a later maintenance failure. Reported tokens are not account quota or dollars.
The input-character limit bounds gathered/digested material, not every tool
read a delegated agent may perform.

### Codex quota (#1843)

With the Codex runner, the notebook reads your Codex plan's own meter: the
weekly window's `used_percent`, its length and when it resets, as
`codex app-server` reports them (`account/rateLimits/read`). Reading it starts
no model turn and costs nothing. Codex reports whole percents, so every figure
below is good to about one point.

- **Every run records the meter before and after** (`quota` in the run log,
  shown by `co rem logs`). The difference is what that run cost in points of
  your week, measured rather than estimated from tokens.
- **Investigation has a weekly budget**, `limits.investigation_quota_points`,
  default **10** points of the weekly window (owner, 2026-09-27). The
  scheduled round adds up the points its investigation runs used since the
  window last reset, and starts no new page once that reaches the budget.
- **Manual investigation counts too** (#1842). `co rem investigate PAGE`,
  `me` and CATEGORY runs record the meter like the round does, and their
  points count toward the same weekly budget. A CATEGORY run stops starting
  pages when the weekly budget is spent, when its own `--budget N` is spent, or
  at the floor, and says which; the page in flight finishes.
- **After init**, `co rem investigate all --budget 10` works whatever init left:
  one queue over people, projects and organisations by weight (the same order
  the round uses), until 10 points of the week are spent. `--list` shows that
  order without running a model.
- **A floor protects your own coding.** No investigation page starts once the
  week is at `limits.quota_floor_percent` or more, default **70%**, however much
  of co rem's budget is left. co rem shares this quota with your real work.
- `co rem status` reads the meter now and says it in two lines, for example
  `Codex week: 5% used on pro; resets Sun 04 Oct 09:49` and
  `Investigation this week: 0 of 20 points; nothing starts once the week is at 70%`.
  `--json` gives the same numbers under `quota` and `investigation_quota`.
- When the meter cannot be read (another runner, Codex not signed in, an older
  Codex), the run says `quota: unknown (<why>)` and the daily call cap
  (`limits.runner_calls_per_day`) is the only bound, as before.

Maintenance is not quota-gated: it is the incremental daily pass and stays
bounded by the call cap. Its cost now shows in points, so a cap can follow
from real numbers. This supersedes the earlier unimplemented 2% initialization
/ 1% daily targets, which needed exactly this meter.

The scheduled daily round maintains first. The first run of the local day then
investigates unfinished pages, most recent activity first, within a reserved
share of the daily attempt cap (8 calls; a person is one investigation); every later run
updates only the people with new mail and the projects with new messages since
the run before, at most 5 pages. Both stop at the weekly budget or the floor and
record how many pages are left ([details](rem-people-pages.md#the-daily-round-four-runs-two-jobs-1723)). Initialization currently builds the map without a model call; manual
investigation remains outside the scheduled cap.

The UI is a static snapshot; run `open` again after changing pages. No merge,
release, new background job, broad mailbox backfill or production co rem rewrite
is implied by the architecture refactor.

See [acceptance evidence](../testing/rem-acceptance.md).

### Inspect one skill's retained run evidence

```bash
co rem --root /path/to/rem investigate skills/catalog/example.md --eval-dir /path/to/.co/evals
```

Skill pages dispatch to a local, deterministic collector instead of the mail/model
investigation pipeline. Omit `--eval-dir` to use `~/.co/evals`; repeat it for
additional summary directories. The collector reads immediate summary YAML files
(up to 1,000 per directory, 4 MB each), matches exact `/skill-name` inputs, and
deduplicates retained run/turn identities. It writes a linked note containing
inputs, retained outputs, reported tool calls, recorded evaluations and coverage.
The skill page gets a managed `Run evidence` block; curated sections and the
existing investigation stamp are preserved. This is evidence gathering, not
a completed quality assessment.

Counts describe observed invocation attempts, not proven starts or lifetime runs.
Tool-invoked skills and other harnesses are not yet covered. Historical outputs
may be missing, current summary model labels may not establish each run's model,
and same-name installed copies cannot be attributed. Goal achievement and
verified changes stay unassessed until actual artifacts are checked.

### 1.8.7 integration update

`co rem --root '<root>' init --days 150` now builds people, projects and installed
skill maps deterministically. The map invokes no model. (Since #1943 init then
writes your own page in a terminal; see Start here.)
Only enabled mail sources are read. Use `subscriptions` and explicit `subscribe`
commands to select sources first. The map records counts, dates and coverage in
`.state/map.json` and writes people/project indexes under `notes/`; it leaves
classification unassessed. The `rem-init` Skill can subsequently rank that map.
Run `investigate <record>` explicitly for one page.

Investigation reads a normalized skeleton and writes a new candidate under
`.state/tasks/`. Only a candidate with valid structure and reference definitions
replaces the page. Failed candidates remain for diagnosis. This check cannot
establish factual correctness. Full source JSON is retained; a readable copy uses
reversible text chunks so line-limited tools can read all of it.

The requirement-to-code/test checklist and remaining decisions are in
[rem-187-checklist.md](rem-187-checklist.md). This update supersedes earlier
references to init launching a model or investigating the owner in the same run;
#1943 later brought back that one step, for the owner's page only, by the owner's decision.

### First-run People and installed Skills

`co rem init` runs without questions in terminals and scripts. It uses connected
mailboxes automatically and prints `co auth google` / `co auth microsoft` tips for
disconnected sources after building the local maps. Authenticate and rerun init
to add People. To restrict mapping to a specific mailbox:

```sh
co rem init --mail outlook
# or: co rem init --mail gmail
co rem init --days 5       # small first-run trial
co rem open
```

This lists 90 days of mail by default: correspondent metadata plus the short
preview the provider lists with each message. A seven-day window that fills the
provider's 200-message listing cap is split until every message in it is
listed, so a busy week is no longer cut off at 200 without a word. Init does not
install a schedule. It subscribes the mailboxes it read, so `start` offers them,
but nothing is read in the background until `start` is approved.

#### Private mail materials

After the map, init saves each listed message body once, so investigating a
person later reads the saved window from disk and only asks the mailbox about
mail outside it. Everything lives under the notebook's `.state/`, which is
owner-only (`0700` directories, `0600` files) and never shown to a model as a
page or sent anywhere:

| File | Holds |
|---|---|
| `.state/source-inventory.md` / `.jsonl` | What was listed, window by window: ids, dates, senders, recipients, subjects, session paths. No bodies, no previews |
| `.state/mail/messages/<provider>/<hash>.json` | One provider-rendered text body per message. Attachments are not downloaded |
| `.state/mail/people/<hash>.jsonl` | Each person page's messages, by reference; a mail to three people is stored once and indexed three times |
| `.state/mail/projects/<hash>.jsonl` | Each project page's local session files, by reference |
| `.state/mail/archive.json`, `summary.md` | Range, counts saved / reused / failed, and status |

Pages never contain a raw body. A body that could not be fetched marks init
`partial` with a nonzero exit; rerunning reuses every saved body and fetches
only the rest. If a later init cannot list a mailbox, the earlier archive is kept
rather than replaced. `--no-mail-archive` skips the body download and keeps the
metadata-only map. Investigating a person reads the archive only when its last
run completed; otherwise it asks the mailbox as before.

A person is named, in this order, by the name they write under, the name in the
owner's saved contacts (Google contacts and "other contacts", Outlook contacts;
skipped when the login cannot read them), and the owner's own greeting in a mail
to that one person ("Hi Larry,", "Larry 你好，", "子明，"). A greeting to several
people names none of them. On the owner's notebook this named 176 of 195 people
the map had titled with a bare address. An organisation is the registrable
domain (accounts.google.com and google.com are one), and a domain only notice
senders write from gets no page. A page still titled by a bare address whose
sender the owner never wrote to is held for review: kept, but left out of the
investigation queue, `co rem list` and the reader's contents. `co rem list
people --review` shows them; a later init that finds a name or a reply from the
owner, or investigating one by its path, brings it back. A nameless address the
owner has written to, the agent's own included, stays an ordinary page, and an
investigated page is never held -- except one the owner only ever writes to and
never hears from, the shape of their own other mailbox: it is held too, and
still asked about with `init --mine` (#1987). A sender whose display name is its
own domain ("Airbnb" <discover@airbnb.com>, "Google Cloud" <googlecloud@google.com>,
"X" <notify@x.com>) and who writes at least three times as often as the owner
answers is a service: listed with the notice senders, no people page, and an
older map's page for it that holds only map output is archived. Someone writing
from their own name at a domain named after them (aaron@aaron.dev) stays a person.
Skills and projects are one page per skill name and per repository (below). With `--mail`, only explicitly selected
mailboxes are read. Missing or failed sources appear in the mapping coverage;
without a selected mailbox the command explains why People is empty.
The terminal shows one line per mapping stage, a short count of People,
Organizations, Projects and Skills, and your own page's facts. Full per-source details stay in `.state/map.json` under the
co rem root and in `--json` output. A custom `--days` window is preserved in the
printed next command and retry tips.

Skills lists one catalog page per name; the page lists each installed copy and
says which differ. The generated index is not counted as another skill.

#### One page per repository

A project is its repository, not each folder a session ran in (#1974). A git
worktree folds into its main checkout's page:

- a folder whose `.git` is a file saying `gitdir: <repo>/.git/worktrees/<name>`
  belongs to `<repo>`;
- a folder under `<repo>/.claude/worktrees/` belongs to `<repo>`, even after
  Claude Code removed it;
- a folder under `.worktree/` or `.worktrees/` that no longer exists belongs to
  the repository beside it whose folder name starts its own
  (`~/projects/.worktree/browser-139` → `~/projects/browser`); with no such
  repository it is left out rather than guessed.

`Paths` lists the repository root and a count, not the worktrees:

```text
## Paths
- /home/you/projects/connectonion
- Worktrees: 49
- Sessions: 116
```

The main checkout is one branch's working tree, not the project's state (#1982).
On the owner's machine it sat on an August branch, and the page said version
1.8.0a3 the week 1.9.0a3 shipped. So an investigation hands the turn one
`checkout-state` item per listed checkout, cited as `git:<path>`: the branch it is
on and its HEAD's commit date, the project's current line (`origin/HEAD`, else
`origin/main`, `origin/master`, `main`, `master`, else the most recently committed
branch) with its last commit date and the version in its `pyproject.toml` or
`package.json`, and -- when HEAD is more than 14 days older than the project's
newest session -- a line saying the checkout's files are not the current state
and the version comes from that line instead. The file list is unchanged; the
turn is told which of what it reads is stale.

Some folders are not projects, and the map leaves them out (`not_a_project` in
`rem/scan.py`):

| Folder | Why |
|---|---|
| your home folder, or above it | it holds every session there is (#1944) |
| inside a hidden folder (`~/.claude/plugins/cache/…`, `~/projects/.artifacts/…`) and not a git repository | a cache, a plugin install or build output |
| a Claude Code scheduled-task folder (`…/scheduled-tasks/…`) | a task's working folder |
| not in a git repository, one session, at most 3 messages you typed | a one-off chat (`create-a-scheduled-task-called-weekday`, a plugin install folder) |

A folder with two sessions, a repository, or a longer conversation stays a
project. System temporary directories, removed Codex worktrees, co rem's own task
copies, fixture notebooks and multi-repository workspace containers stay out as
before.

A notebook mapped before this has split and junk pages. The next map merges
them: every existing page listing one of the repository's paths (worktrees
compared as their main checkout) folds into one page — the one with the most
written content, so an investigated page is never merged into an empty one.
Written lines of the other page are merged section by section with citations
renumbered, its message material under `.state/projects/` is merged too, and the
page itself moves to `.state/archived/` with its record kept as an alias
(`.state/aliases.json`). A junk folder's page that holds only map output is
archived; one somebody wrote in is kept.

### Preview reliability checks

Initialization reports partial failure with a nonzero exit if a selected mail source cannot be initialized or read. Completed maps remain available; provider error text is not exposed. Recovery commands retain the notebook root. Automated-looking correspondents are explicitly labelled candidates, not silently certified as people.

init runs the whole `co rem investigate me` for you. `--quick` is a bounded
pass that samples recent items across available source types and labels the
result partial; it is only for `me`, and neither mode approves a candidate
without review.

`co rem investigate <page> --days 5` reports source gathering, evidence
preparation, extraction chunk counts when the material exceeds one model turn,
and candidate writing in its run log and terminal. A failed model or provider
call exits nonzero and keeps the page unchanged. Project investigations may
inspect a bounded set of files in the page's recorded local Paths; the file
inventory is a lead, not proof of file contents. Review the candidate and its
citations before treating it as a verified notebook page.
Completed extraction chunks are checkpointed under `.state/extracts/investigate/`;
rerunning the same evidence and model settings can reuse them after an
interruption. The running log records the current chunk and usage from completed
chunks. A changed source or extraction prompt invalidates the checkpoint.

Repeated mapping refreshes generated project counts, dates and paths while preserving written notes. Skill pages retain authored descriptions and show current installed metadata in a separate managed section. Unchanged content is not rewritten. Equivalent SSH/HTTPS Git remotes share an identity; distinct case-sensitive repository paths remain distinct. Search groups skill installations just like the catalog, and the homepage labels its content as a snapshot rather than claiming every skeleton is maintained.

## Reflections, review and staged investigation

See [co rem memory workflows](rem-memory.md) for `reflect`, `review`, `capture`,
`route` and `daily`, including provider, retention and budget limits.
