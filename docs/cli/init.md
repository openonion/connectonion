# ConnectOnion Init Command

`co init` sets up global credentials. Project initialization requires an
explicit directory, such as `co init ./`.

## Quick start

```bash
co init --yes                     # ~/.co/keys.env and the global identity
co init ./ --yes                  # configuration in this existing project
co init /path/to/project --yes    # configuration in another existing project
co init ./ --template co-ai       # also add the hosted agent template
```

The path must name an existing directory. Use `co create my-agent` to create a
new directory with the default `co-ai` template.

## Global setup: no path

Plain `co init` creates or reuses the signing identity in `~/.co/keys/` and
attempts managed-key authentication, saving credentials to `~/.co/keys.env`.
It does **not** create or modify the current directory's `.env`, `.co/`,
`agent.py`, or other project files—even when run inside an existing project.

Existing global provider credentials are preserved. An explicit `--key`
saves that provider key globally; keys merely present in the process environment
or loaded from a project are not copied into global storage. Avoid putting
secrets into shell history; editing the private keys file is also supported.

If authentication cannot complete, local identity setup remains available and
the command tells you to run `co auth` later. Successful local initialization
does not mean managed models or email are authenticated.

## Project setup: explicit path

`co init ./` uses the global identity and initializes the selected directory.
It does not mint a separate project keypair.

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

Global setup scripts can keep `co init --yes`. `co create` is unchanged.
At runtime, explicit process variables take precedence over the selected
project's `.env`, which takes precedence over global `~/.co/keys.env`.
See [CLI reference](README.md) for authentication and credential diagnostics.
