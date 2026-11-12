> **Preview 1.9.3rc26.** Shared initialization and repair behavior described below ships in this opt-in preview; stable remains 1.9.2. See [release notes](https://github.com/openonion/connectonion/releases/tag/v1.9.3rc26).

# ConnectOnion Init Command

`co init` prepares the local identity, profile, coding-agent integration and REM. Project initialization requires an
explicit directory, such as `co init ./`.

## Quick start

```bash
co init                           # identity, profile, skills, command index and first REM notebook
co init --yes                     # same prompt-free global setup
co init --no-rem                  # skip REM setup
co init ./ --yes                  # configuration in this existing project
co init /path/to/project --yes    # configuration in another existing project
co init ./ --template co-ai       # also add the hosted agent template
```

The path must name an existing directory. Use `co create my-agent` to create a
new directory with the default `co-ai` template.

## Global setup: no path

Plain `co init` creates or reuses the signing identity in `~/.co/keys/` and
attempts managed-key authentication, saving credentials to `~/.co/keys.env`.
It also creates a missing `~/.co/agent.json` local profile. Your existing profile
is kept; use `co setup --name my-agent --bio "My work" --no-skills` to customize
only those fields.

### Codex CLI and browser sign-in

Global `co init` (including `--no-rem`) finds Codex in this order:

1. `codex` on PATH;
2. `/Applications/ChatGPT.app/Contents/Resources/codex-cli/bin/codex`;
3. `/Applications/Codex.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS/codex`.

An explicit `CODEX_CMD` override is kept. A previous standalone install in
`~/.local/bin/codex` is also reused when that directory is absent from PATH.
The same lookup is used by REM's `codex exec` turns and `co rem doctor`.

If none is available, init uses the [official OpenAI standalone installer](https://github.com/openai/codex#installing-and-running-codex-cli)
for macOS and Linux. It downloads the script over HTTPS from
`https://chatgpt.com/codex/install.sh`, saves it temporarily, and runs `sh` with
`CODEX_NON_INTERACTIVE=true` and `CODEX_INSTALL_DIR="$HOME/.local/bin"`.
The [installer](https://github.com/openai/codex/blob/main/scripts/install/install.sh)
checks release SHA-256 digests before installing. No npm, Homebrew, sudo or
installation prompts are required. The equivalent manual command is:

```bash
curl -fsSL https://chatgpt.com/codex/install.sh | CODEX_NON_INTERACTIVE=true sh
```

Only if the standalone attempt fails, init tries `npm install -g @openai/codex`
when npm is available, then `brew install --cask codex` on macOS when Homebrew
is available. The summary reports the reused path, installed version and path,
or failure reason with the exact retry command. It also prints an undo line.
The standalone installer may add a `Codex installer` PATH block to your shell
profile; open a new terminal to use bare `codex`. ConnectOnion can use the full
installed path immediately, including in scheduled turns.

Init checks `<resolved CLI> login status`. If needed, it runs `<resolved CLI>
login`, which opens the browser for your ChatGPT sign-in. It waits at most 45
seconds for that attempt, then checks status again. Cancellation, failure or an
unfinished browser login leaves the rest of init running. REM uses its ready
Claude Code fallback after checking `claude auth status --json`; otherwise it records that scheduling is
waiting for Codex login, completes the local notebook setup, and prints the
exact login command followed by `co rem start`. An existing notebook and its
schedule are preserved on repeated init.

To undo a standalone install, remove `~/.local/bin/codex`,
`~/.local/bin/codex-code-mode-host`, and `~/.codex/packages/standalone/`
(or the printed package path if `CODEX_HOME` is set), then remove the block
between `# >>> Codex installer >>>` and `# <<< Codex installer <<<` in your
shell profile. Keep `auth.json`, sessions and your other Codex settings.
Scheduled jobs preserve `CODEX_HOME` and `CODEX_CMD` when set.
Package-manager installations use `npm uninstall -g @openai/codex` or
`brew uninstall --cask codex`.

### REM setup

Global `co init` asks no setup questions; a missing Codex login opens the browser. It prepares `~/.co/rem`, records an init
consent grant for local Codex / Claude Code sessions and every authenticated
Google and Microsoft mailbox, installs upkeep using the usual scheduler
(Codex exec via launchd on macOS, systemd user timer on Linux), and builds
the first notebook in the foreground. The cost estimate is information, with
no confirmation pause. `--yes` and runs without a terminal do the same work.
Without a mailbox it continues on sessions and prints `co auth google` /
`co auth microsoft`. A mailbox connected later joins the next scheduled round
automatically; a source explicitly removed stays removed.

The final output names the scheduler and explains how to undo setup:
`co rem stop` turns scheduling off; `co rem sources` lists sources and
`co rem sources remove SOURCE` removes one; `co auth logout` removes OpenOnion
credentials. There is no mailbox disconnect command in `co auth`; revoke
mailbox access in your Google or Microsoft account. After stopping upkeep,
delete `~/.co/rem` to remove the notebook.

`--no-rem` skips REM, rerunning global init leaves existing REM unchanged,
and `--background` uses the same REM step. Use `co rem init` to rerun the
notebook build. Without a supported scheduler, init still builds and explains
how to schedule manual sync. See [REM: Start here](rem.md#start-here).

It does **not** create or modify the current directory's `.env`, `.co/`,
`agent.py`, or other project files—even when run inside an existing project.

Existing global provider credentials are preserved. An explicit `--key`
saves that provider key globally; keys merely present in the process environment
or loaded from a project are not copied into global storage. Avoid putting
secrets into shell history; editing the private keys file is also supported.

If authentication cannot complete, local identity setup remains available and
the command tells you to run `co auth` later. Successful local initialization
does not mean managed models or email are authenticated.

### Telling Codex and Claude Code that `co` exists

`co init`, `co init ./`, `co create` and `co setup` all do two things for the coding agents on this machine,
only for those installed (their `~/.codex` or `~/.claude` directory exists):

- runs `co skills link`, so ConnectOnion's bundled skills appear in
  `~/.codex/skills/` and `~/.claude/skills/`;
- writes ConnectOnion's command index into `~/.codex/AGENTS.md` and
  `~/.claude/CLAUDE.md`, between `<!-- co:begin <version> -->` and
  `<!-- co:end -->`. It is generated from the CLI: a few rules (use `co
  commands` and `co <cmd> --help` before a browser or a script; do not hunt
  for credentials) and one line per top-level command.

It prints each path it changed. A directory it cannot write, like `~/.codex`
inside Codex's sandbox, is skipped with a line saying so, and init still
finishes; run `co skills link` and `co skills index` outside the sandbox later.
Your own skill directories are kept, including when project init uses `--force`.
Your own text outside the markers is never touched. To take the block out: `co skills index --remove`; to refresh it
without re-running init: `co skills index`. Agents started with `host()` or
`co ai` refresh a stale block on their own, and `co doctor` reports one that
is missing or stale. See [co skills index](skills.md#co-skills-index).

### Rerun to repair missing setup

Initialization checks these files on every run, including when a signing key
already exists. It restores a missing `keys.env` from that identity, creates a
missing local profile, repairs dangling bundled-skill symlinks, and connects a coding
agent installed since the previous run. It preserves the existing identity,
profile, user skill directories and instruction text outside the generated block.
It does not require a separate `co skills link` after project initialization.

The global directory defaults to `~/.co/`; an explicit process
`AGENT_CONFIG_PATH` selects its identity, profile and user skill library together.
Browser installation and publishing remain separate commands. REM uses
`~/.co/rem`, the same default as `co rem`, independently of `AGENT_CONFIG_PATH`.

## Project setup: explicit path

`co init ./` uses the global identity and initializes the selected directory.
It also completes the same local profile, skills and command-index setup as
plain init. It does not mint a separate project keypair or initialize REM.

| File | Behavior |
|---|---|
| `.env` | Create or append missing credentials; preserve existing provider and application values |
| Identity entries in `.env` | Refresh from global identity, including after `co reset` |
| `CO_INVITE_CODE` | Create once per project; preserve on subsequent runs |
| `.co/host.yaml` | Create project configuration if missing |
| `.co/docs/` | Refresh bundled framework documentation |
| `.co/admins.txt` | Record the creating identity as an admin |
| Template files such as `agent.py` | Only with `--template`; preserve existing files unless `--force` |
| `.gitignore` | Add secret/runtime exclusions when initializing inside a Git repository |

Personal Google/Microsoft OAuth credentials and machine-specific configuration
paths are not copied from global keys into a project. Keep both `.env` and
`keys.env` out of source control.

```bash
# Add configuration without generating agent.py
co init ./ --yes

# Add the hosted template
co init ./ --template co-ai --yes

# Generate a custom agent
co init ./ --template custom --description "Monitor a site and alert me"

# Refresh configuration and bundled docs without selecting a code template
co init ./ --yes
```

Non-empty and special directories prompt for confirmation unless `--yes` is
given. `--yes` does not authorize overwriting existing template code;
`--force` does. Treat refreshed `.co/docs/` as generated framework reference,
not a place for personal notes.

## Options

| Option | Meaning |
|---|---|
| `PATH` | Optional existing project directory; omission selects global setup |
| `--key` | Explicit provider key: global storage without PATH, project configuration with PATH |
| `--yes`, `-y` | Skip project confirmation prompts |
| `--template`, `-t` | Project only: `co-ai` or `custom`; omitted means configuration only |
| `--description` | Project only: description for a custom template |
| `--force` | Project only: allow replacing existing template files |

Project-only options without PATH fail before writing files and show an example
using `co init ./`.

## Migrating scripts

Commands that formerly relied on implicit project initialization must add a path:

```bash
# Before: co init --yes --template co-ai
co init ./ --yes --template co-ai
```

Global setup scripts can keep `co init --yes`. `co create` now completes the
same local coding-agent setup when it creates a project.
At runtime, explicit process variables take precedence over the selected env
file, which is global `~/.co/keys.env` unless `co --env-file PATH` names a
project file; there is no per-key fallback between files. `co env` shows what
the selected file holds and `co env set` edits it.
See [CLI reference](README.md) for authentication and credential diagnostics.


In preview 1.9.3rc26, rerunning initialization also refreshes a bundled skill
symlink into an older installed ConnectOnion package. Personal skill directories
and links outside installed package layouts are preserved. Missing local profile
fields receive defaults; invalid skill metadata is kept and reports how to repair
it. All four entry points share this preparation.
