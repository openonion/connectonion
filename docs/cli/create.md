> **Preview 1.9.3rc22.** Shared initialization and repair behavior described below ships in this opt-in preview; stable remains 1.9.2. See [release notes](https://github.com/openonion/connectonion/releases/tag/v1.9.3rc22).

# co create — Start a new agent project

`co create` makes a new project directory with the hosted `co-ai` template and
completes the local identity, profile, bundled skill links and coding-agent
command indexes. You can start from this command without running `co init` first.

```bash
co create my-agent --yes
cd my-agent
co host
```

The name must be a new directory. To initialize an existing directory, use
`co init ./ --yes` or add `--template co-ai` for template code.

## What it prepares

| Scope | Files and behavior |
|---|---|
| Machine | Create or reuse the identity in `~/.co/keys/`; repair `keys.env` when missing |
| Local profile | Create a missing `~/.co/agent.json`; keep existing profile edits |
| Coding agents | Link bundled skills into installed Codex/Claude Code and refresh their generated command indexes |
| New project | `agent.py`, template dependencies and container files, `.env`, `.co/host.yaml`, framework docs and the control center |
| Project access | Create a project invite code and record the creating identity as an admin |
| Git repository | Add secret and runtime exclusions to `.gitignore` |

Projects use the machine identity; they do not get a new signing keypair.
Existing global setup does not skip the coding-agent checks. A missing link or a
coding agent installed later is connected when another project is created.
User skill directories and custom instruction text outside the generated index
are preserved.

Managed-key authentication is attempted when no managed token is recorded.
If the backend is unavailable, creation can continue with local setup and your
own provider keys. Local completion does not prove a managed token is valid.
See [co init](init.md) for the shared local setup and credential boundaries.

## Templates

| Template | Purpose |
|---|---|
| `co-ai` | Default hosted agent; specialize its role and project skills |
| `custom` | Generate `agent.py` from a description using an available model key |

```bash
co create my-agent --template co-ai --yes
co create site-monitor --template custom --description "Monitor a site and alert me"
```

Custom generation calls a model. The default template copies the bundled source.
Old template names such as `minimal` and `browser` are no longer available; the
CLI lists the supported choices when a template is unknown.

## Options

| Option | Meaning |
|---|---|
| `NAME` | New project directory; omit to choose a suggested name |
| `--template`, `-t` | `co-ai` (default) or `custom` |
| `--description` | What a custom agent should do |
| `--key` | Explicit provider key for this project |
| `--yes`, `-y` | Skip interactive prompts |

An existing directory is refused before identity creation or authentication, with
a suggested free name. Existing projects can be refreshed using `co init ./`.
For profile customization and importing separate skills, see [co setup](setup.md).
