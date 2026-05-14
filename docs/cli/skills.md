# co skills - Discover & Import Skills

Scan skill files across your AI coding agents (Claude Code, Codex, Cursor, Kiro) and import the ones you want into `~/.co/skills/` so ConnectOnion can use them.

## Quick Start

```bash
# Scan every known agent skill directory
co skills discover

# Pull a discovered skill into ~/.co/skills/
co skills copy ship-feature

# See what's already imported
co skills list
```

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

When merging into `agent.json`, any prior `signature` / `signer` fields are removed because the content changed and must be re-signed. Each generated skill entry has `publish: false` by default; existing `publish` values are preserved on refresh.

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
- [Built-in Skills](../useful_skills/) — Skills that ship with ConnectOnion
- [Skills plugin](../useful_plugins/skills.md) — Runtime auto-discovery
