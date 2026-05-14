# co setup - Global Identity & Skill Library Setup

One command to set up everything in `~/.co/` that you need to publish an agent: identity keypair, `agent.json` profile, and a populated skill library scanned from every coding agent on your machine.

## Quick Start

```bash
co setup --name my-alias --bio "One-line description of what I do"
```

## What `~/.co/` looks like after `co setup`

```
~/.co/
├── keys/
│   ├── agent.key        # Ed25519 private key (signing identity)
│   ├── agent.pub        # Public key
│   └── recovery.txt     # 12-word recovery phrase
├── keys.env             # OPENONION_API_KEY (after `co auth`)
├── agent.json           # ← NEW: your publishable profile
│                        #   {address, alias, name, bio, skills:[...], version}
└── skills/              # ← populated from claude/codex/cursor/kiro
    ├── index.json       # discovery cache (where each skill came from)
    └── <name>/SKILL.md  # one dir per discovered skill
```

There is **no separate "bundle" directory**. `~/.co/` itself is what `oo-publish` reads from at publish time.

## What it does (in order)

1. **Identity.** If `~/.co/keys/agent.key` is missing, runs `co init --yes` in a temp directory to bootstrap one (the temp dir prevents `agent.py` / `.co/host.yaml` pollution).
2. **`~/.co/agent.json`.** Writes the profile with your signing address, alias, bio, and `skills[]`. Skips profile creation if the file already exists unless you pass `--force` (which backs up to `agent.json.bak`).
3. **Skill library.** Runs `co skills discover && co skills copy --all && co skills manifest`. Idempotent — existing skills are not overwritten without `--force`; skill metadata is merged into `agent.json` with `publish: false` by default.
4. **Auth check.** Reports whether `OPENONION_API_KEY` is in `keys.env`. If not, suggests `co auth` (publishing works without it; only the `co/*` managed models require it).

## Options

| Option | Short | Description |
|--------|-------|-------------|
| `--name` | `-n` | Alias for `agent.json` (default `$USER` lowercased) |
| `--bio` | `-b` | One-line bio for `agent.json` |
| `--force` | `-f` | Overwrite existing `agent.json` (backs up to `.bak`) |
| `--no-skills` |  | Skip the skill library refresh |

## Examples

### First-time setup

```bash
co setup --name writing-tools --bio "Skills for nonfiction writing and editing"
```

Output:
```
✓ Identity: 0xcd92510bb6cc090374ecc345ef8c19b9d3797624fd1fbf7e078a9372fc31bdc1
✓ Wrote /Users/you/.co/agent.json (alias=writing-tools)

Refreshing ~/.co/skills/ library...
              Discovered skills (57)
... (table) ...
Index written to /Users/you/.co/skills/index.json
✓ Copied 30 skill(s) → /Users/you/.co/skills
✓ Merged 30 skill(s) into /Users/you/.co/agent.json

✓ Auth: OPENONION_API_KEY present

Setup complete. Run the oo-publish skill to sign + announce.
```

### Refresh Skill Library Only

```bash
co skills discover && co skills copy --all && co skills manifest
```

Use `co setup --no-skills` only when you want to create or refresh `agent.json` without touching `~/.co/skills/`.

### Change alias / bio after the fact

```bash
co setup --name new-alias --bio "Updated bio" --force
# → backs up old agent.json to agent.json.bak
```

You can also just edit `~/.co/agent.json` directly — it's normal JSON. `oo-publish` reads whatever's there at sign time.

## Idempotency

`co setup` is safe to re-run:
- Identity is never regenerated if `~/.co/keys/agent.key` exists.
- `agent.json` is skipped if it exists (use `--force` to overwrite).
- Skill library is refreshed — new skills are added, existing ones are skipped (use `co skills copy --all --force` separately for hard refresh), and `agent.json.skills` is updated.

## How `co setup` relates to `co init`

| Command | Scope | What it creates |
|---------|-------|-----------------|
| `co init` | **Project** (cwd) | `agent.py`, `.env`, `.co/host.yaml`, vibe-coding docs |
| `co setup` | **Global** (`~/.co/`) | `agent.json`, `skills/`, `keys/` (if missing) |

They're orthogonal. Use `co init` to scaffold a new agent *project* (with template code). Use `co setup` to prepare your *identity* for publishing. Both can run on the same machine without conflict.

## See Also

- [co init](README.md#co-init---add-to-existing-directory) — Project scaffold (different scope)
- [co skills](skills.md) — The discover/copy/manifest commands that `co setup` orchestrates
- publishing workflow — Higher-level flow that signs and announces `~/.co/agent.json`
