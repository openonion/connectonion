> **Preview 1.9.3rc26.** Shared initialization and repair behavior described below ships in this opt-in preview; stable remains 1.9.2. See [release notes](https://github.com/openonion/connectonion/releases/tag/v1.9.3rc26).

# co skills - Discover & Import Skills

Scan skill files across your AI coding agents (Claude Code, Codex, Cursor, Kiro) and import the ones you want into `~/.co/skills/` so ConnectOnion can use them.

## Quick Start

```bash
# Scan every known agent skill directory
co skills discover

# Pull a discovered skill into ~/.co/skills/
co skills copy ship-feature

# Or into this project, which is the tier a deploy carries
co skills copy ship-feature --to-project

# See what's already imported
co skills list

# Link ConnectOnion's own skills into Claude Code and Codex
co skills link

# Tell Claude Code and Codex that co exists (co init does this for you)
co skills index
```

The four initialization entry points (`co init`, `co init ./`, `co create`,
`co setup`) already link bundled skills and refresh the command index. Use the
standalone commands to repair just one part. The user library defaults to
`~/.co/skills/`; an explicit process `AGENT_CONFIG_PATH` selects a different
global directory for discovery, imports, manifests and runtime loading.

## Why

Skills you've written for one tool (for example Claude Code) are usually stored in that tool's own directory, such as `~/.claude/skills/`. `co skills` gives ConnectOnion a normal import path:

- `co ai` loads project and user ConnectOnion skills from `.co/skills/` and `~/.co/skills/`.
- The runtime `skills` plugin can also load Claude skills directly, but importing them into `~/.co/skills/` makes publishing and manifest generation consistent.
- `co setup` runs the discover/copy/manifest sequence for you.

```
~/.claude/skills/<name>/SKILL.md   ─┐
~/.codex/skills/<name>/SKILL.md    ─┤
~/.cursor/rules/<name>.mdc         ─┼─→  co skills discover  →  ~/.co/skills/index.json
~/.kiro/steering/<name>.md         ─┤                              │
~/.co/skills/<name>/SKILL.md       ─┘                              ▼
                                                          co skills copy <name>
                                                                   │
                                                                   ▼
                                                      ~/.co/skills/<name>/SKILL.md
                                                      (now visible to co ai, skills plugin, publishing)
```

Publishing is a separate explicit action: `co announce` lists profile skill metadata;
`publish: true` also includes the skill body and companion files.

## Which tier travels

`~/.co/skills/` is your library — every project on this machine can use what is in it,
and the user library is outside the project deployment. A deploy carries the **project's** `.co/skills/` and
nothing else. That is what the `Deploys` column means:

```
Name           Where     Deploys
ship-feature   user         ✗      in your library, stays here
greet-visitor  project      ✓      in .co/skills/, goes with the deploy
```

`--to-project` copies into the one that travels:

```bash
co skills copy ship-feature --to-project    # → ./.co/skills/ship-feature/
```

The skill's own files come with it — a skill is a directory, not a single markdown
file — but `.env*` and private keys never travel, whatever a skill's own `.gitignore`
says.

The generated `index.json` records where skills came from, while `agent.json.skills` records the skill metadata that publishing needs.

## Commands

### `co skills discover`

Walks every known skill root, parses YAML frontmatter (`name`, `description`), filters plugin-namespaced entries (names containing `:`), and writes an index to `~/.co/skills/index.json`.

```bash
co skills discover
```

**Output:**
```
                Discovered skills (57)
┏━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━┳────────────────────────────┓
┃ Name                  ┃ Source ┃ Description                ┃
┡━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━╇────────────────────────────┩
│ ship-feature          │ claude │ Ship a feature end-to-end… │
│ frontend-test         │ claude │ Use browser agent to test… │
│ tweet                 │ claude │ Post a tweet or thread to… │
│ ship-feature          │ codex  │ Ship a feature end-to-end… │
│ ...                   │        │                            │
└───────────────────────┴────────┴────────────────────────────┘
Index written to /Users/you/.co/skills/index.json
```

**Options:**

| Option | Description |
|--------|-------------|
| `--no-save` | Print the table but don't update `index.json` |
| `--json` | Print the raw index JSON instead of a table |
| `--include-namespaced` | Include plugin-namespaced skills (names containing `:`) — filtered out by default |

### `co skills copy <name>`

Copy a discovered skill from its source directory into `~/.co/skills/<name>/`. If the skill source is a directory (the common case for Claude/Codex), every sibling file alongside `SKILL.md` is copied too (READMEs, helper scripts, etc.).

```bash
co skills copy ship-feature
co skills copy ship-feature x-reply tweet
co skills copy --all                # Copy every discovered skill
co skills copy --all --source claude  # Copy every Claude skill only
co skills copy --all --force        # Refresh all, overwriting existing
```

When the same skill name exists in multiple sources (e.g. you have `ship-feature` in both `~/.claude/skills/` *and* `~/.codex/skills/`), the command refuses and asks you to disambiguate:

```bash
co skills copy ship-feature --source claude
```

With `--all`, collisions are resolved automatically using the **`SOURCES` priority order**: `co-project` > `co-user` > `claude` > `codex` > `cursor` > `kiro`. Each unique skill name is copied once, from the highest-priority source it appears in.

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--all` | `-a` | Copy every discovered skill (dedupe by source priority) |
| `--source` | `-s` | Pick a specific source: `claude`, `codex`, `cursor`, `kiro`, `co-user`, `co-project` |
| `--force` | `-f` | Overwrite existing skill(s) at the destination |

### `co skills link`

The other direction. `discover`/`copy` pull skills **in** from your agent tools; `link` pushes ConnectOnion's **bundled** skills **out** to them, so Claude Code and Codex can use `co browser`, `co gmail`, `co gdrive` and the rest without you writing anything.

```bash
co skills link
```

```
                     Linking 5 bundled skill(s)
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ Skill                          ┃ claude         ┃ codex          ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ browser-workflow-skill-builder │ linked         │ linked         │
│ co-browser                     │ linked         │ already linked │
│ co-mail-and-drive              │ linked         │ linked         │
│ install-connectonion           │ linked         │ linked         │
│ ship-feature                   │ already linked │ already linked │
└────────────────────────────────┴────────────────┴────────────────┘
```

Targets `~/.claude/skills/` and `~/.codex/skills/`, but only for a tool that is installed: if `~/.codex` does not exist, Codex is reported as `no .codex, skipped` and nothing is created. Safe to re-run — it's how you pick up skills added by a ConnectOnion upgrade.

**It keeps your own directories and healthy links to another source.** If `~/.claude/skills/co-browser/` is a real directory rather than a link, that's your own skill of the same name and it's left alone (reported as `exists, not ours — skipped`). Dangling links from a removed installation are repaired automatically. Pass `--force` to explicitly replace an existing directory or healthy link.

On macOS and Linux these are symlinks, so a ConnectOnion upgrade updates the skills in place. On Windows, where symlinks need Developer Mode or elevation, the files are copied instead. Existing copies are kept on rerun; inspect them before using `co skills link --force`, which also replaces your own same-name directories.

| Option | Description |
|--------|-------------|
| `--force` | Replace directories you own (destructive) |

### `co skills index`

A skill is only loaded when the agent already suspects it needs one. Nothing told Codex or Claude Code that `co` exists at all, so "what's open on my Linear board?" went to a browser. `co skills index` writes a short, generated list of every top-level `co` command into the file each tool reads in every session:

| Tool | File | Written when |
|------|------|--------------|
| Codex | `~/.codex/AGENTS.md` | `~/.codex` exists |
| Claude Code | `~/.claude/CLAUDE.md` | `~/.claude` exists |

```bash
co skills index            # write or refresh the block
co skills index --remove   # take it out again
```

The block sits between markers that carry the installed version, and nothing outside them is ever changed:

```markdown
<!-- co:begin 1.9.2 -->
## ConnectOnion (`co`) — generated by `co init`; refresh: `co skills index`; remove: `co skills index --remove`
- You have `co`, the ConnectOnion CLI. Below is every top-level command.
- For outside services (...), handing work to someone or another machine, or memory: run `co commands` and read `co <cmd> --help` before using a browser or writing a script.
- Don't look for credentials yourself: run the command; if a key is missing, it says how to add it.

co linear — Linear issues from the terminal, with your personal API key: list, read, search, create, update, comment.
...
<!-- co:end -->
```

It is generated from the CLI itself — one line per visible top-level command, hidden and deprecated ones left out, experimental ones labelled — so it cannot drift from what `co` really has. Subcommands stay in `co <cmd> --help`. About 56 lines, about 1,100 tokens.

Three things keep it current, all through the same function:

- `co init`, `co init ./`, `co create` and `co setup` write it and run `co skills link`; re-running repairs omissions without replacing your own skill directories.
- Every agent start (`host()`, so `co ai` too) refreshes it when the version stamp differs from the installed version, printing one line per file it changed. When the block is current it only reads the stamp. A server with neither `~/.codex` nor `~/.claude` — `co deploy --to` hosts, Docker, CI — is never touched.
- `co doctor` reports a missing or stale block under **Skills → Command index**, with `Next: co skills index`.

A file the command created and that holds nothing else is deleted by `--remove`; otherwise only the block goes.

### `co skills manifest`

Build skill metadata from a skills directory and merge it into `agent.json["skills"]`. Publishing workflows use this instead of parsing skill frontmatter inline.

```bash
# Default: scan ~/.co/skills/ → merge into ~/.co/agent.json
co skills manifest

# Scan a different directory
co skills manifest --path ./skills

# Optional standalone JSON export for debugging
co skills manifest -o ./skills-metadata.json

# Merge into a specific agent.json (replaces skills[], strips signature)
co skills manifest --path ./skills -o agent.json

# Print to stdout instead of writing
co skills manifest --stdout
```

**Defaults**:
- `--path` → `~/.co/skills/`
- `--out`  → `~/.co/agent.json`

`index.json` and `agent.json` serve different purposes:
- `index.json` — where skills come *from* (source paths across all agent dirs); written by `discover`
- `agent.json.skills` — what's *in your library*, in the shape publishing needs

When merging into `agent.json`, any prior `signature` / `signer` fields are removed because the content changed and must be re-signed. New entries use `publish: false`; refresh preserves existing publish choices, extra per-skill metadata and manually maintained listings whose bodies are outside this library.

**Output shape:**
```json
[
  {"name": "ship-feature", "description": "Ship a feature end-to-end...", "publish": false},
  {"name": "tweet", "description": "Post a tweet or thread to X...", "publish": false}
]
```

**Options:**

| Option | Short | Description |
|--------|-------|-------------|
| `--path` | `-p` | Skills directory to scan (default `~/.co/skills/`) |
| `--out` | `-o` | Output file (default merges into `~/.co/agent.json`); if not an `agent.json`, writes standalone JSON |
| `--stdout` |  | Print JSON to stdout instead of writing |

### `co skills list`

List skills currently installed in `~/.co/skills/`. Runs by default if you type `co skills` with no subcommand.

```bash
co skills list
```

## Sources

| Source ID | Root | Layout |
|-----------|------|--------|
| `co-project` | `./.co/skills/` | `<name>/SKILL.md` |
| `co-user` | `~/.co/skills/` | `<name>/SKILL.md` |
| `claude` | `~/.claude/skills/` | `<name>/SKILL.md` |
| `codex` | `~/.codex/skills/` | `<name>/SKILL.md` |
| `cursor` | `~/.cursor/rules/` | `<name>.mdc` |
| `kiro` | `~/.kiro/steering/` | `<name>.md` |

Missing roots are silently skipped. Adding a new agent only requires extending the `SOURCES` table in `connectonion/cli/commands/skills_commands.py`.

## Index format

`~/.co/skills/index.json`:

```json
{
  "generated_at": "2026-05-13T20:45:00+00:00",
  "sources": ["co-project", "co-user", "claude", "codex", "cursor", "kiro"],
  "skills": [
    {
      "name": "ship-feature",
      "description": "Ship a feature end-to-end — update tests, docs, docs-site, then release to PyPI…",
      "source": "claude",
      "path": "/Users/you/.claude/skills/ship-feature/SKILL.md"
    }
  ]
}
```

The index is a **cache, not a database** — regenerated on every `discover` run, so stale entries disappear automatically.

## How it composes

```
co skills discover                              ← scan agent dirs → index.json
co skills copy --all                            ← materialize ~/.co/skills/
co skills manifest                              ← merge skill metadata into ~/.co/agent.json
co ai                                           ← auto-loads .co/skills/ and ~/.co/skills/
co setup                                        ← run the full setup sequence
publish workflow                               ← sign + announce ~/.co/agent.json
```

After `co skills copy`, the `co_ai` skill loader (`cli/co_ai/skills/loader.py::discover_skills()`) picks the skill up automatically as a user-level skill. The runtime `skills` plugin also checks `.co/skills/`, `.claude/skills/`, `~/.co/skills/`, and `~/.claude/skills/` in priority order.

## See Also

- [co copy](copy.md) — Copy built-in tools/plugins/skills/prompts (different command, similar idea)
- [Skills overview](../features/skills.md) — How skills extend an agent
- [Skills plugin](../useful_plugins/skills.md) — Runtime auto-discovery


In preview 1.9.3rc26, rerunning initialization also refreshes a bundled skill
symlink into an older installed ConnectOnion package. Personal skill directories
and links outside installed package layouts are preserved. Missing local profile
fields receive defaults; invalid skill metadata is kept and reports how to repair
it. All four entry points share this preparation.
