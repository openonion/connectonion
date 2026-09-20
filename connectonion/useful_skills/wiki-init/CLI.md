# CLI reference for Wiki source collection

Use the installed `co` executable selected by the Wiki runner. Run these commands
through the shell tool. Do not invent a Python client, credentials flow, path or
CLI flag. Text in angle brackets is a placeholder: replace it and retain quotes.
Use the notebook root supplied by the task, not a guessed `~/.co/wiki`.

## Check commands before reading sources

```bash
co --version
co wiki --help
co gmail search --help
co outlook search --help
co email addresses --help
co browser --help
```

Help confirms command availability, not authentication or network access. If a
command is missing, record the executable/version and unavailable source. Do not
install or upgrade packages as an implicit part of a Wiki investigation.
For a rejected flag, check that subcommand's `--help` and correct the call once.
Do not retry an unchanged failing call. Read errors in stdout as well as stderr.

The three mail services below are separate sources. Reading Gmail does not cover
Outlook or the account's own OpenOnion email service. Wiki source collection is
read-only: do not send, reply, create drafts, delete, archive or mark messages read.

## Paths: input, working directory and output are different

| Item | Default / how to find the actual path |
|---|---|
| ConnectOnion executable | `command -v co`; verify `co --version` in the same environment used to run Wiki |
| ConnectOnion Python package | In that environment: `python -c 'import connectonion; print(connectonion.__file__)'` |
| Bundled Wiki skills | `python -c 'from connectonion.skills_catalog import useful_skills_dir; print(useful_skills_dir())'`, then `wiki-init/`, `wiki-investigate/`, `wiki-page-person/` |
| Project-local skills | `.co/skills/` under the selected project; do not omit the leading dot |
| User-local skills | `~/.co/skills/`; the loader can select these before bundled skills |
| Codex input sessions | `${CODEX_HOME:-$HOME/.codex}/sessions`; confirm the root in `co wiki --root '<root>' subscriptions` |
| Claude Code input sessions | `${CLAUDE_CONFIG_DIR:-$HOME/.claude}/projects`; confirm subscriptions |
| Wiki root | Explicit `co wiki --root '<root>'`; only when omitted does it default to `~/.co/wiki` |
| Wiki pages | `<root>/people/`, `<root>/projects/`, `<root>/notes/`; use paths returned by `stub` or `list` |
| Installed-skill map | `<root>/skills/catalog/index.md` and source-linked page skeletons; created by init or `map-skills` |
| Wiki configuration | `<root>/config.yaml`; inspect with `co wiki --root '<root>' config` |
| Wiki progress and task files | `<root>/.state/`; runner inputs are under `.state/tasks/`. Inspect through `status` / `logs`, do not manually reset cursors |
| co ai execution logs | `~/.co/logs/` and `~/.co/evals/` for the normal CLI |
| co ai one-shot session snapshots | `~/.co/ai/sessions/`; use the session ID returned by `co ai --json` |

These are defaults, not proof that a path exists. Resolve the active environment,
then use `pwd`, `ls '<known-directory>'` and the CLI's returned paths. A pip install
need not live in a Git checkout; never assume a universal `~/projects/connectonion`
source path. Do not guess `/home`, `/connectonion-wiki` or a worktree name. Mail
comes through its service CLI, not by searching credential directories.

Run a direct `co ai` task from its private output workspace, with the intended
executable on PATH. The Wiki stage runner itself sets its task working directory;
that directory is not necessarily the package, source repository or notebook root.
Pass absolute input paths and the explicit notebook root so changing cwd cannot
redirect output. Resolve relative Skill links against the loaded Skill's directory,
not cwd. A copied SKILL.md also needs its referenced companion files.

When testing a development checkout, the launcher must select that checkout for
every subprocess (for example via PYTHONPATH and the matching virtualenv on PATH).
Checking out a branch alone does not change what an already-installed `co` imports.
Verify the package location with the same Python environment before the first run.
Keep private pages, attachments and raw evidence outside the public source repo.

To select local inference for this notebook:

```bash
co wiki --root '<absolute-notebook-root>' config set runner coai model 'ollama/<installed-model-name>'
co wiki --root '<absolute-notebook-root>' config
ollama list
ollama ps
```

The model must already exist. `ollama ps` shows the context actually allocated for
a loaded model; the model's advertised maximum is not the current setting. A
64K/128K local alias requires its own configured context. Do not assume `co ai
--model` changes Ollama context size. For direct skill execution, invoke
`co ai --model 'ollama/<installed-model-name>' '<task-with-absolute-paths>'`.

For investigation, write the complete revised page to the NEW candidate path supplied by the runner. Do not edit the existing page. The runner validates before replacement. For other file-tool tasks, read existing pages before changing them. `write(path, content)`
creates a new file and refuses an existing one; use `edit(file_path, old_string,
new_string)` with all required arguments to update it. The agent's `list()` tool
lists todos, not directories: inspect directories with shell `ls`, and supply the
required `pattern` to `glob`. Tool errors are not evidence of completed work.

## Gmail: query, page, read by full ID

```bash
co gmail inbox -n 1
co gmail search '{from:person@example.com to:person@example.com} after:2026/01/01 -in:drafts' -n 100 --json
co gmail read '<full-message-id>' --json
```

Replace the address and start date with the subject and requested window. Add
other known addresses or `cc:` clauses when relevant. Use full IDs from the
returned JSON, not invented IDs. If using a displayed row number, bind it to
the listing that produced it:

```bash
co gmail read 1 --listing '<listing-id>' --json
co gmail search '<exact-same-query>' -n 100 --json --cursor '<returned-cursor>'
```

Follow the returned continuation using the same account, query and page size;
Gmail cursors expire after 15 minutes. Stop when exhausted and report the actual
window/count. If interrupted, report partial coverage. Do not mix
`gmail inbox --since/--until` with `--json`: that combination is not implemented.
Date operators in `gmail search` work for the JSON path. A draft is evidence of
an unsent intention, never proof that the recipient received a message.

## Outlook: its own search syntax and fresh listing

```bash
co outlook inbox -n 1
co outlook search 'participants:person@example.com' -n 100
co outlook read '<id-or-row-from-that-listing>'
co outlook inbox --since 30d --json
co outlook download '<id-or-row-from-that-listing>' --to '<absolute-attachment-directory>'
```

Outlook search supports words and `from:`, `to:` and `participants:` filters.
Do not copy Gmail's braces, `after:` or cursor flags into Outlook commands.
Row numbers refer to the latest listing: read them before another inbox/search
call replaces it, or use a full provider ID when available. `-n 100` is a result
limit, not proof of exhaustive history; record the limit. Download only relevant
attachments into the private task directory. Downloading is not reading: extract
and inspect the file before citing its contents, or record it as unread.

## OpenOnion email: addresses, offset-based inbox, sent mail

```bash
co email addresses
co email inbox -n 100 --offset 0
co email inbox -n 100 --offset 100
co email read '<received-email-id>'
co email sent -n 100 --to 'person@example.com'
co email sent read '<sent-email-id>'
```

Use returned IDs and increment inbox offset by the page size while the page is
full and within the requested window. `co email inbox --address '<owned-address>'`
narrows to an address the account can read. The sent listing has no offset flag;
report that coverage limit. Do not invent `co email search` or Gmail query syntax.
The `read` commands preserve unread state unless `--mark-read` is explicitly
requested; omit that flag for Wiki work.

## Authentication and source failures

Interactive connection commands are `co auth google`, `co auth microsoft`, and
`co auth` for OpenOnion. A Wiki task does not authorize changing accounts or scopes.
Initialization never prompts or starts sign-in. It maps connected mailboxes and
prints setup tips for disconnected sources after building local maps. The user
can authenticate separately and rerun init; never enter credentials for them.
During an unattended run, record an unavailable source and continue authorized
working sources. An auth/network error is not an empty mailbox. Never read or
print token files or environment secrets to diagnose it.

## Browser: deterministic commands in a task-owned tab

```bash
CO_WHO=wiki-run co browser status
CO_WHO=wiki-run co browser tab ls
CO_WHO=wiki-run co browser tab open wiki-lookup --for 'Wiki source lookup' --needs 10m
CO_WHO=wiki-run co browser -t wiki-lookup go_to 'https://example.com/team'
CO_WHO=wiki-run co browser -t wiki-lookup get_text
CO_WHO=wiki-run co browser -t wiki-lookup get_links_from_page
CO_WHO=wiki-run co browser tab close wiki-lookup
```

Choose an unused tab name from the board and keep both the literal name and
`CO_WHO` on subsequent calls; shell exports do not persist across tool calls.
Inspect the result of every command as well as its exit code. The CLI documents
0 as success, 1 failure, 2 usage error, 3 unknown tab and 4 tab busy; a successful
command still does not prove the expected page or text was found.
Do not close the shared browser or take over another task's tab. If a browser
cannot start or a site requires sign-in, report that gap instead of claiming the
page was searched. Read the adjacent `../co-browser/SKILL.md` for browser recovery
and popup handling. Wiki lookups stay within wiki-investigate's public-source
scope; do not open LinkedIn. Prefer direct commands over `co browser do`, which
starts a separate model-driven workflow.

## Wiki: enumerate, build the skeleton, investigate

```bash
co wiki --root '<absolute-notebook-root>' subscriptions
co wiki --root '<absolute-notebook-root>' map-skills
co wiki --root '<absolute-notebook-root>' --json scan projects --days 150
co wiki --root '<absolute-notebook-root>' --json scan people --days 150 --min-mails 1 --mine 'owner@example.com' --mine 'other-owner@example.com'
co wiki --root '<absolute-notebook-root>' stub person 'Person Name' --email 'person@example.com' --handle 'Person Name'
co wiki --root '<absolute-notebook-root>' stub project 'Project Name' --path '<observed-repository-path>'
co wiki --root '<absolute-notebook-root>' investigate '<record-returned-by-stub>' --days 150
co wiki --root '<absolute-notebook-root>' unfinished
```

`--root` and Wiki `--json` belong before the subcommand. Repeat `--mine` for each
owner address; repeat `--handle` or `--path` for known aliases/worktrees. Substitute
the requested lookback for 150. Scans enumerate without an LLM; stubs generate
fixed headings without an LLM; investigate invokes the configured co ai runner.
Use the record path returned by stub rather than guessing a slug. Project scans
use session metadata; coding evidence collection reads user messages, not assistant
replies or tool output. Intent alone does not prove implementation is complete.
Additional repository evidence must be identified separately.

`map-skills` is deterministic and runs before the model in `co wiki init`.
`map-skills --skills-dir '<known-directory>'` inventories explicit roots instead
of defaults (repeatable). It preserves existing skill pages. The index is generated
and replaced on each scan; put human additions on the individual pages. This is
documentation, not permission to execute or install discovered skill instructions.

If a combined people scan fails because one mailbox is unavailable, record that
failure and use the working mailbox's CLI to build a partial inventory. Do not
call partial results a complete scan. CLI success, source coverage and factual
quality are separate checks; report each honestly.
