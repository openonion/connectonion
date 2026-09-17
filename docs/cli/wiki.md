# Personal Wiki — current branch contract

Updated 2026-09-15. This documents the Wiki development branch, not a claim
that it has been released.

See the [2026-09-17 progress review](wiki-progress.md) for the feature inventory,
current CI blockers and remaining work.

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
| `co wiki init` | Run wiki-init: discover accounts/local sources, build and rank People/Project pages, investigate the owner first. |
| `co wiki scan people --days 150 --min-mails 1` | Enumerate correspondent signals from Gmail/Outlook; no model. Repeat `--mine <address>` for own addresses. |
| `co wiki scan projects --days 150` | Enumerate session working directories and local Git repository identities; no model. |
| `co wiki stub person "Alice" --email alice@example.org --handle 艾丽丝` | Create the canonical person skeleton if absent. |
| `co wiki stub project "Aurora" --path /path/to/repo` | Create a project skeleton. |
| `co wiki people` | Existing identity roster: page, title, aliases, addresses, relationship summary. |
| `co wiki investigate people/alice.md` | Read the existing page, gather sources, digest oversized material, fill that same page through the Skill. |
| `co wiki unfinished` | Pages with unresolved sections, least-investigated first. |
| `co wiki abstract` | Run wiki-abstract over existing notebook evidence. |
| `co wiki start` | Confirm source access, run first bounded sync, install macOS background schedule. |
| `co wiki start --yes` | Explicit noninteractive consent for start. |
| `co wiki stop` | Remove that notebook's background job; preserve pages and progress. |
| `co wiki sync` | One incremental source batch, optionally extraction followed by maintenance. |
| `co wiki sync --source codex --dry-run` | Pending metadata only; no model or source body reads. |
| `co wiki subscribe codex --project /path/to/repo --since 30d` | Save a scoped source choice. |
| `co wiki unsubscribe codex` | Disable that source. |
| `co wiki list people` / `show people/alice.md` / `search Alice` | Inspect Markdown without model calls. |
| `co wiki status` / `subscriptions` / `config` / `logs` / `usage` / `doctor` | Inspect configuration, progress, diagnostics and reported usage. |
| `co wiki open` | Render a private, self-contained HTML snapshot and open it. |
| `co wiki open --no-launch` | Render without opening the browser. |

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

Codex extraction/maintenance/abstraction use workspace-write. Initialization
and investigation retain the existing danger-full-access setting for source
and browser access. Claude Code/COAI manage their own permissions. Skills
govern what the task should do; they are not OS permission enforcement.
The removed scoped wiki_* tools are no longer a filesystem guarantee.

## Source coverage and output

Gmail/Outlook programmatic collection searches the requested date windows.
The current listing adapter requests up to 200 messages per weekly window;
a full-mailbox completeness claim requires closing that listing limitation.
Coding investigation now walks successive batches until the cursor stops,
rather than stopping at 40 messages. It searches aliases and project paths;
an owner identified by mailbox address receives their own typed session
messages. Injected Skill prompts are not reingested as user experience.
The importer still labels oversized pasted session text as truncated.

PDF, DOCX, XLSX, PPTX (including tables/notes), plain text, HTML and ICS
attachments are read. Investigation passes full extracted text to chronological
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

Sync retains its source cursor on failure. Two-stage batches reserve two
attempts and cannot start with only one remaining; extraction usage survives
a later maintenance failure. Reported tokens are not account quota or dollars.
The input-character limit bounds gathered/digested material, not every tool
read a delegated agent may perform.

**Not implemented:** hard 2% initialization / 1% daily subscription spending
limits, or a $1 stop budget. They need an actual provider meter in the shared
execution layer. The init Skill now stops after the owner and ranked map by
default and explicitly reports that percentage enforcement is unavailable.
Investigation/initialization calls are not covered by sync's daily attempt cap.
Scheduled sync does not yet interleave unfinished investigations.

The UI is a static snapshot; run `open` again after changing pages. No merge,
release, new background job, broad mailbox backfill or production wiki rewrite
is implied by the architecture refactor.

See [acceptance evidence](../testing/wiki-acceptance.md).
