# Personal Wiki — current branch contract

Updated 2026-09-24. The Wiki ships in the opt-in 1.8.8 previews and becomes
long-term supported in 1.9.0 (#1664 names it first). The command surface and
every `--help` page are the agreed design in #1656; the pages themselves live
in `connectonion/cli/commands/wiki_help.md` and a test holds them to the code.
Old command names (`unfinished`, `people`, `daily`, `subscribe`, `subscriptions`,
`unsubscribe`, `route`, `usage`) still work until 1.9 and print their new name.

See the [2026-09-17 progress review](wiki-progress.md) for the feature inventory,
current CI blockers and remaining work.

## Start here

```bash
co wiki                      # Read the guide and local status; does not initialize
co wiki init                 # Build People, Organizations, Projects and Skills maps
co wiki investigate          # List your actual pages; does not run a model
```

Copy the `Next:` command printed by `investigate` to investigate one existing
page. You can also supply an exact title or email when it identifies one page,
for example `co wiki investigate 'Ody'` if that person exists in your notebook.
Ambiguous names list the matching paths and do not start a model. Example page
names in old help text, such as `people/emma.md`, are not built-in records.
`--help` displays help and exits, even when you also supply a page name.

```bash
co wiki investigate          # What is left to investigate, by category; no model
co wiki investigate me --quick --days 5  # Bounded first pass; disclose uncovered sources
co wiki open                 # Open the full-page Wiki in your browser
co wiki sync --dry-run       # Inspect pending metadata, without running a model
co wiki sync                 # One update: new material, then at most one unfinished page
co wiki logs                 # Inspect results, partial coverage and failures
```

Normal output uses readable labels and plain page paths. Empty lists explain
what is missing; unknown usage remains **Unknown**, never zero. Results end
with a copyable `Next:` command, including the selected root and shell quoting.
Use `co wiki --help` as the workflow guide: it gives task selection,
observed inputs, expected results, source/quality checks and recovery before
the command inventory. `init --help`, `investigate --help` and `sync --help`
explain their full workflow as well as options. The overview and group help
share one implementation, so human and agent guidance cannot drift separately. Root and JSON flags belong **before** the subcommand:

```bash
co wiki --root '/path/to/my wiki' investigate
co wiki --root '/path/to/my wiki' --json status
```

Explicit `--json` retains the `ok`, `data`, and `next` envelope for scripts.
No-argument `--json` continues to return status, without the human guide.
Piping human output does not hide the next step. Grouped help covers:

| Task | Commands |
|---|---|
| Map and investigate | `init`, `investigate`, `unfinished`, `map-skills`, `scan`, `stub` |
| Browse | `open`, `list`, `show`, `search`, `people`, `status` |
| Update and review | `sync`, `daily`, `capture`, `reflect`, `reflections`, `propose`, `review`, `abstract` |
| Sources and background | `subscriptions`, `subscribe`, `unsubscribe`, `start`, `stop` |
| Settings and diagnostics | `route`, `logs`, `usage`, `doctor`, `config`, `config set` |

`start` explicitly authorizes collection and installs background maintenance
plus at most one unfinished-page investigation per local day when the day's
call budget allows;
`init` does neither. A mapped page is not an investigated or quality-approved page.
For an initial trial, `co wiki init --days 5` preserves the same five-day
window in its suggested next command. `investigate me --quick` samples recent
evidence, takes one synthesis turn, and marks its coverage as partial. A full
owner investigation can read substantially more material and cost much more.

## Installed-skill skeletons at initialization

`co wiki init` deterministically builds People, Organizations, Projects and Skills pages from
their canonical templates and available source metadata before any model
investigation. Unknown fields remain explicit; investigation is a separate step.
See the [initialization interaction contract](wiki-init-contract.md).

Its coverage lines keep the four source states apart, because each one needs a
different next command:

```text
gmail: metadata only, 150 days, at most 200 messages per seven-day window; 42 correspondents
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
co wiki --root /private/path/to/wiki map-skills
co wiki --root /private/path/to/wiki map-skills --skills-dir /known/project/.co/skills
```

The generated `skills/catalog/index.md` links to one documentation skeleton per
distinct source file. Metadata seeds the name, description and original path;
usage, inputs/outputs, related projects and history await evidence. Same-name
files remain distinct; aliases resolving to the same source are deduplicated.
Reruns preserve page content and retain pages whose source disappeared. Only the
generated index is refreshed. Original `SKILL.md` files are not changed or run, and `skills/approved/` remains
write-protected. Catalog pages now include a fenced, verbatim source snapshot
after the overview, with the original path, snapshot time and SHA-256. Rebuilding
refreshes only the generated snapshot/metadata block and preserves authored notes.
Unchanged snapshots keep their timestamp; missing sources retain the last snapshot.
Snapshots that exceed the page limit or trigger existing secret-shaped-content
protection are explicitly reported as unavailable, never silently truncated.

Defaults cover the co/Claude skill search roots, conventional agent/Codex skill
roots, and co ai's bundled default allowlist. This is a shallow inventory, not
an exhaustive plugin-cache or remote-catalog scan. Repeat `--skills-dir` for
explicit roots; supplying it replaces defaults for that scan. Coverage and
unreadable files are reported in the index and command result.

The [Wiki CLI reference](../../connectonion/useful_skills/wiki-init/CLI.md) explains
mail IDs, browser tabs, source/working/output directories and failure recovery.

## One execution path

```text
User / scheduler
      |
      v
co wiki init / investigate / sync / abstract
      |
      | stage Skill + source Skill + page shape + material paths
      v
co ai --json --harness <codex | claude-code | ours> /wiki-<stage>
      |
      +-- Codex tool       --> Codex subscription
      +-- Claude Code tool --> Claude Code subscription
      +-- COAI agent       --> configured LLM provider (including Ollama)
      |
      v
Markdown pages + reported usage + observed file changes
```

COAI already delegates before creating its own LLM loop. Selecting Codex
therefore does not spend a COAI model turn deciding to delegate. All Wiki
stages, including extraction and maintenance, use that same command.

Wiki's former app-server subclass, dynamic wiki_* tools, isolated Codex HOME,
auth-file copying, native version/config checks and direct native extraction
path have been removed. The shared COAI native adapters remain: their job is
to speak Codex or Claude Code's protocol once for all callers.

Wiki retains source importers, bounded digest batches, page templates,
identity roster, progress, sync locking/accounting, OS scheduling and the
reader. A shell can call the public CLI; rewriting these data operations as a
second shell implementation would duplicate behavior.

## Commands

Group options precede the command: `co wiki --root /path/to/wiki --json list`.
Every command returns a next command, including in JSON and through a pipe.

| Command | Behavior |
|---|---|
| `co wiki init` | Run wiki-init: discover accounts/local sources, build and rank People/Project/Skills pages; investigation is a separate follow-up. |
| `co wiki scan people --days 150 --min-mails 1` | Enumerate correspondent signals from Gmail/Outlook; no model. Repeat `--mine <address>` for own addresses. |
| `co wiki scan orgs --days 180 --min-people 2` | List work domains that two or more people write from — where an organisation page earns its place. No model. |
| `co wiki scan projects --days 150` | Enumerate session working directories and local Git repository identities; no model. |
| `co wiki stub person "Alice" --email alice@example.org --handle 艾丽丝` | Create the canonical person skeleton if absent. |
| `co wiki stub org "UNSW" --domain unsw.edu.au --person people/vern-chan.md` | Create an organisation skeleton; `People here` holds links, not copies. |
| `co wiki stub project "Aurora" --path /path/to/repo` | Create a project skeleton. |
| `co wiki list people --aliases` | Existing identity roster: page, title, aliases, addresses, relationship summary. |
| `co wiki investigate people/alice.md` | Read the existing page, gather sources, digest oversized material, fill that same page through the Skill. |
| `co wiki investigate` | What is left to investigate, by category, most useful first. No model. |
| `co wiki investigate people --limit 3` | Investigate up to three unfinished people pages, most mail first; `--list` prints the order and runs nothing. Also `projects`, `orgs`, `skills`. |
| `co wiki investigate me` | Fill your own page from what you sent and your coding sessions of the last 30 days. |
| `co wiki abstract` | Run wiki-abstract over existing notebook evidence. |
| `co wiki start` | Confirm source access, run first bounded sync, install macOS background schedule. Asks again whenever anything its summary shows (sources, runner, model, permissions, schedule, limits) changed since the last approval. A start after `stop` resumes the schedule without a batch; `co wiki sync` runs one. |
| `co wiki start --yes` | Explicit noninteractive consent for start. |
| `co wiki stop` | Remove that notebook's background job; preserve pages and progress. |
| `co wiki sync` | The whole update: one batch of new material, then at most one unfinished page. What the schedule runs (`sync --scheduled`). |
| `co wiki sync --source codex --dry-run` | Pending metadata only; no model or source body reads. |
| `co wiki sources add codex --project /path/to/repo --since 30d` | Save a scoped source choice. |
| `co wiki sources add whatsapp --chat <id>` | Read one WhatsApp chat (group or person) from the files `co whatsapp listen` keeps; ids from `co whatsapp chats`. Repeat per chat; the next `co wiki start` shows it and asks before anything is read. `co wiki sources remove whatsapp --chat <id>` stops one chat. |
| `co wiki sources remove codex` | Disable that source. |
| `co wiki list people` / `show people/alice.md` / `search Alice` | Inspect Markdown without model calls. |
| `co wiki status` / `sources` / `config` / `logs` / `logs --usage` / `doctor` | Inspect configuration, progress, diagnostics and reported usage. |
| `co wiki open` | Open the full-page private Wiki through the current `co ai` Host when its identity is configured; otherwise open a local snapshot. |
| `co wiki open --local` | Render and open the self-contained local HTML snapshot. |
| `co wiki open --no-launch` | Return the page address without opening the browser. |

`init` is the foreground Skill workflow. `start` remains the explicit
background lifecycle command; initialization does not install a schedule.
Map is a stage inside wiki-init, not a separate model runner.

Map reads known information before leaving basic fields unknown. It uses the
single person-page definition; investigation reads that same existing page,
keeps supported facts and fills gaps. The owner is investigated first.
Automated notices are signals for the Skill to classify, not an automatic
rule to discard companies or event opportunities.

## Choose a harness

```bash
co wiki config set runner codex model gpt-5.6-luna
co wiki config set runner claude-code model default
co wiki config set runner coai model co/gemini-3.8-flash
co wiki config set runner coai model ollama/qwen3
```

A model name must be available in the selected provider/account. `default`
omits the model flag. Changing runner without a model chooses that harness's
default. Old coai configs which retained the unused Codex default migrate to
their previous effective behavior (COAI's default). No credential belongs in
Wiki configuration.

Equivalent direct CLI delegation, useful in a shell script:

```bash
co ai --json --harness codex --model gpt-5.6-luna \
  "/wiki-investigate Update /path/to/wiki/people/alice.md; read its current content first."
```

The direct Skill call does not run Wiki's deterministic source collection or
advance its sync cursor. Use `co wiki investigate` for that orchestration.
COAI expands the Skill name and supplies its installed directory.

Every Wiki model turn starts from the fixed `.state/tasks/` workspace inside
the selected Wiki root (`~/.co/wiki` by default). Codex therefore groups
those turns under one workspace in its history. Inputs, review results and
disposable page copies live in per-run subdirectories there;
the runner validates a candidate before promoting it to the notebook.

Every Wiki stage reads text other people wrote -- mail bodies and PDF, DOCX
and XLSX attachments -- and the daily job `co wiki start` installs runs with
nobody watching. So every stage, scheduled or started by hand, runs confined:

| Runner | Flags Wiki passes to `co ai` | What the model can do |
|---|---|---|
| `codex` | `--sandbox workspace-write` | Read files; write only inside `.state/tasks/` and TMPDIR; no network |
| `claude-code` | `--permission-mode acceptEdits` | Read and write inside `.state/tasks/`; commands, web fetch/search and reads elsewhere are denied, since nobody is there to approve them |

`co wiki start` shows the row for the configured runner in its consent
summary, as `model_permissions`, before you approve the schedule, and
`model_receives` names whose login the model is called through (Codex or
Claude Code). Change the runner later and the next `start` shows the
summary again.

Model turns and the launchd job both run the installation that is running
`co wiki` -- `<its python> -m connectonion.cli.main` -- not the first `co` on
PATH. Starting from a non-activated venv with an older `co` in `~/.local/bin`
used to install a job, and route every model turn, through the older one.

Wiki's own code fetches the mail and attachments before the model starts, so
the model needs nothing more than to read that material and write the page
copy it is given. The cost is the web: investigation no longer looks up a
role or a switchboard number with `co browser`, and says so in the page's
`Uncertainties`. Before 1.8.8 investigation ran Codex with
`danger-full-access` and Claude with `bypassPermissions`, which gave anyone
who could email the user an unattended agent with a shell, the network and
the user's mailbox; a line in the prompt was the only defence.

Wiki removes an ambient `ANTHROPIC_API_KEY` from Claude's subprocess
environment so the run uses the selected account's subscription rather than
silently billing the API. Skills govern what the task should do; they are not
OS permission enforcement.
The removed scoped wiki_* tools are no longer a filesystem guarantee.

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

PDF, DOCX, XLSX, PPTX (including tables/notes), plain text, HTML and ICS
attachments are read; XLSX needs `pip install 'connectonion[wiki]'`, and
without it a spreadsheet is named as unread with that command. Investigation passes full extracted text to chronological
digest chunks instead of dropping a long attachment's tail. Unreadable
formats/errors remain visible. The Skill supplements from the account's
`co email` service, known documents and public sites, and reports what it
could not search. Own-mail sent history currently has no paginated CLI;
Jira discovery/auth is not connected to this Wiki entry point yet.

Each task supplies material and composed instructions as files, avoiding
OS argv size limits. File changes are observed on disk, including deletions
and partial changes on failure; a success sentence is not a file-change count.
Extraction returns its written notes file, not a commentary/status reply.
Nonzero exits, missing/malformed envelopes, provider errors and timeouts fail
the task. Investigation is not marked finished on a failed execution.

Wiki forwards its delegated deadline as `co ai --timeout SECONDS` and gives
the outer process 15 seconds to exit afterward. The common native adapter
therefore closes its delegate before the Wiki process timeout is reached.

## Scheduling and accounting

launchd invokes the resolved `co wiki --root ... sync --scheduled` CLI every
five minutes, with PATH entries for co and installed delegates. Saved local
time slots determine whether a batch is due. Repeated start reloads one job;
missed slots coalesce into one catch-up. No permanent Wiki daemon is added.

Each notebook root is its own job, `ai.openonion.co-wiki.<hash of the root>`,
the default `~/.co/wiki` included, so `co wiki start`/`stop` under another
`HOME` never touches your real job. A job installed before 1.8.8b12 under
the bare label `ai.openonion.co-wiki` is still found: `stop` removes it and
`start` replaces it, but only when its own `--root` is this notebook.

Sync retains its source cursor on failure. Two-stage batches reserve two
attempts and cannot start with only one remaining; extraction usage survives
a later maintenance failure. Reported tokens are not account quota or dollars.
The input-character limit bounds gathered/digested material, not every tool
read a delegated agent may perform.

**Not implemented:** hard 2% initialization / 1% daily subscription spending
limits, or a $1 stop budget. They need an actual provider meter in the shared
execution layer. The init Skill now stops after the owner and ranked map by
default and explicitly reports that percentage enforcement is unavailable.
The scheduled daily round maintains first, then attempts at most one unfinished
page per local day. It reserves a bounded number of investigation calls within
the same daily attempt cap and leaves room for later maintenance slots when
possible. Initialization currently builds the map without a model call; manual
investigation remains outside the scheduled cap.

The UI is a static snapshot; run `open` again after changing pages. No merge,
release, new background job, broad mailbox backfill or production wiki rewrite
is implied by the architecture refactor.

See [acceptance evidence](../testing/wiki-acceptance.md).

### Inspect one skill's retained run evidence

```bash
co wiki --root /path/to/wiki investigate skills/catalog/example.md --eval-dir /path/to/.co/evals
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

`co wiki --root '<root>' init --days 150` now builds people, projects and installed
skill maps deterministically. It invokes no model and performs no investigation.
Only enabled mail sources are read. Use `subscriptions` and explicit `subscribe`
commands to select sources first. The map records counts, dates and coverage in
`.state/map.json` and writes people/project indexes under `notes/`; it leaves
classification unassessed. The `wiki-init` Skill can subsequently rank that map.
Run `investigate <record>` explicitly for one page.

Investigation reads a normalized skeleton and writes a new candidate under
`.state/tasks/`. Only a candidate with valid structure and reference definitions
replaces the page. Failed candidates remain for diagnosis. This check cannot
establish factual correctness. Full source JSON is retained; a readable copy uses
reversible text chunks so line-limited tools can read all of it.

The requirement-to-code/test checklist and remaining decisions are in
[wiki-187-checklist.md](wiki-187-checklist.md). This update supersedes earlier
references to init launching a model or investigating the owner in the same run.

### First-run People and installed Skills

`co wiki init` runs without questions in terminals and scripts. It uses connected
mailboxes automatically and prints `co auth google` / `co auth microsoft` tips for
disconnected sources after building the local maps. Authenticate and rerun init
to add People. To restrict mapping to a specific mailbox:

```sh
co wiki init --mail outlook
# or: co wiki init --mail gmail
co wiki init --days 5       # small first-run trial
co wiki open
```

This reads correspondent metadata for the initialization window, not mail bodies,
and does not install a schedule or enable ongoing mail collection. With `--mail`, only explicitly selected
mailboxes are read. Missing or failed sources appear in the mapping coverage;
without a selected mailbox the command explains why People is empty.
The terminal shows mapping stages and a short count of People, Organizations,
Projects and Skills. Full per-source details stay in `.state/map.json` under the
Wiki root and in `--json` output. A custom `--days` window is preserved in the
printed next command and retry tips.

Skills lists one catalog entry per name. Open it to inspect each installed copy
and its source path; implementations may differ. All underlying pages, links and
annotations are preserved. The generated index is not counted as another skill.
Project discovery excludes system temporary directories and removed Codex worktrees.
It also excludes Wiki task copies under any notebook's `.state/tasks` and
generated fixture notebooks, plus workspace containers holding multiple Git
repositories, so repeated runs do not turn scratch pages or the enclosing
projects folder into separate projects.

### Preview reliability checks

Initialization reports partial failure with a nonzero exit if a selected mail source cannot be initialized or read. Completed maps remain available; provider error text is not exposed. Recovery commands retain the notebook root. Automated-looking correspondents are explicitly labelled candidates, not silently certified as people.

After init, the suggested `co wiki investigate me --quick` is a bounded first
pass: it samples recent items across available source types and labels the
result partial. Remove `--quick` for a comprehensive owner investigation;
that can take several extraction turns and substantially more time and model
usage. `--quick` is only for `me`, and neither mode approves a candidate
without review.

`co wiki investigate <page> --days 5` reports source gathering, evidence
preparation, extraction chunk counts when the material exceeds one model turn,
and candidate writing in its run log and terminal. A failed model or provider
call exits nonzero and keeps the page unchanged. Project investigations may
inspect a bounded set of files in the page's recorded local Paths; the file
inventory is a lead, not proof of file contents. Review the candidate and its
citations before treating it as a verified Wiki page.
Completed extraction chunks are checkpointed under `.state/extracts/investigate/`;
rerunning the same evidence and model settings can reuse them after an
interruption. The running log records the current chunk and usage from completed
chunks. A changed source or extraction prompt invalidates the checkpoint.

Repeated mapping refreshes generated project counts, dates and paths while preserving written notes. Skill pages retain authored descriptions and show current installed metadata in a separate managed section. Unchanged content is not rewritten. Equivalent SSH/HTTPS Git remotes share an identity; distinct case-sensitive repository paths remain distinct. Search groups skill installations just like the catalog, and the homepage labels its content as a snapshot rather than claiming every skeleton is maintained.

## Reflections, review and staged investigation

See [Wiki memory workflows](wiki-memory.md) for `reflect`, `review`, `capture`,
`route` and `daily`, including provider, retention and budget limits.
