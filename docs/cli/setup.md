> **Preview 1.9.3rc26.** Shared initialization and repair behavior described below ships in this opt-in preview; stable remains 1.9.2. See [release notes](https://github.com/openonion/connectonion/releases/tag/v1.9.3rc26).

# co setup — Customize your profile and import skills

`co init` prepares the local identity, a default profile, bundled skill links and
coding-agent command indexes. Use `co setup` to customize that profile and import
skills you keep in other coding tools.

```bash
co setup --name my-alias --bio "What I work on"
```

`--no-skills` skips library discovery, copying and manifest generation. It still
repairs the identity, default profile, bundled skill links and command indexes.

To prepare just that local integration without importing your library:

```bash
co setup --no-skills
```

## What setup prepares

| Item | Behavior |
|---|---|
| `~/.co/keys/` | Reuse the machine identity; create one when missing |
| `~/.co/keys.env` | Repair a missing file without rotating the identity; attempt managed-key auth for a new identity |
| `~/.co/agent.json` | Create a missing profile; explicit `--name` and `--bio` update only those fields |
| Bundled skill links | Link into installed Codex and Claude Code; keep your own skill directories |
| Generated command index | Refresh the marked block in the coding agents' instruction files; keep your own text |
| `~/.co/skills/` | Discover and import your library unless `--no-skills` |
| `agent.json.skills` | Generate metadata from that library, retaining existing publish choices |

Setup runs this preparation in the current CLI process. It does not need another
installed copy of `co` on PATH. Every invocation checks for missing pieces even
when the identity already exists.

The default global directory is `~/.co/`. An explicit process
`AGENT_CONFIG_PATH` selects the identity, profile and user skill library together;
`co skills` and the runtime skills plugin read the same library.
Global `co setup` does not accept a project `--env-file` selector; it rejects one
before creating or repairing files.

## Preserve edits or recreate the profile

```bash
# Update only the named fields; keep other profile metadata
co setup --name writing-tools --bio "Tools for writing" --no-skills

# Recreate the complete profile, backing up the old file to agent.json.bak
co setup --name writing-tools --bio "Tools for writing" --force --no-skills
```

Without profile options, an existing profile is kept. Updating profile fields
removes a prior signature so the changed profile can be signed again.
`--force` recreates the profile; it does not replace user skill directories or
force-copy the imported library. To explicitly refresh an imported skill, use
`co skills copy <name> --force`.

## Import a skill library

The default setup runs:

```bash
co skills discover
co skills copy --all
co skills manifest
```

Existing imported skills are kept. New manifest entries use `publish: false`;
existing publish choices, manual listings and extra skill metadata survive. Review the profile and library before announcing:

```bash
co skills list
co announce --dry-run
```

`--dry-run` shows the proposed announcement without sending it. Setup itself
does not publish a profile. See [co skills](skills.md) for source precedence and
what travels with a project.

## Authentication and recovery

Setup reports whether an OpenOnion token is present, without printing it or
claiming that the server has verified it. A missing token leaves local setup
available and prints `co auth` as the recovery action. A read-only coding-agent
directory is skipped with a repair command to run from a writable shell.

```bash
co auth
co skills link
co skills index
```

## Options

| Option | Meaning |
|---|---|
| `--name`, `-n` | Set alias and name; default for a new profile is `$USER` |
| `--bio`, `-b` | Set the bio; omitted fields in an existing profile stay unchanged |
| `--force`, `-f` | Recreate `agent.json`, backing up the old profile |
| `--no-skills` | Skip importing the user library; keep basic integration repair |

Use [co init](init.md) for local initialization, `co init ./` for an existing
project, or [co create](create.md) for a new project directory. Each completes the
same local integration, so the starting command does not leave skills unlinked.


In preview 1.9.3rc26, rerunning initialization also refreshes a bundled skill
symlink into an older installed ConnectOnion package. Personal skill directories
and links outside installed package layouts are preserved. Missing local profile
fields receive defaults; invalid skill metadata is kept and reports how to repair
it. All four entry points share this preparation.
