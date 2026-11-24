# REM's credential sandbox

`connectonion/rem/sandbox_profile.py` keeps any Codex run that REM launches from reading the
owner's credentials. REM's night dispatch builds prompts from untrusted mail, and runs with
network on, so a prompt-injected run that can read `~/.co/keys.env` can also send it out.
`codex exec -s workspace-write` does not stop that: its seatbelt limits writes and reads the
whole disk.

Status: module and tests exist; nothing calls it yet. The night dispatch and the night
investigations adopt it in their own branches.

## How a caller uses it

```python
from connectonion.rem.sandbox_profile import wrap

argv, protected = wrap(
    [codex, 'exec', '-s', 'danger-full-access', '-C', str(root), ...],
    allow_co=[task_dir],          # subpaths of ~/.co this run may read and write; default none
    deny=[other_worktree],        # extra paths to hide
    writable=[root, *add_dirs],   # where the run may write; required when wrapping Codex
)
if not protected:
    ...  # Linux: argv is unchanged. Surface it (a doctor line); never run as if protected.
```

`prefix(**same_options)` returns just the `/usr/bin/sandbox-exec -p <profile>` head;
`profile(home=None, **same_options)` returns the SBPL text.

**Wrap Codex with `-s danger-full-access`, never `workspace-write`.** Codex's own seatbelt
cannot start inside ours: every shell call fails with `sandbox_apply: Operation not permitted`.
`writable=` moves the workspace write limit into this profile instead, so the outer profile is
the only sandbox and it confines Codex, its tools and its MCP servers alike. Evidence:
`docs/testing/rem-sandbox-profile-results.md`.

## What is denied

Reads and writes, by real path (each resolved with realpath; `/tmp` becomes `/private/tmp`):

- `~/.co`, apart from the `allow_co` subpaths
- `~/.ssh`, `~/.config/gh`, `~/.aws`, `~/.gnupg`, `~/Library/Keychains`, `~/.docker`,
  `~/.kube`, `~/.config/gcloud`, `~/.azure`, `~/.claude` (other agents' sessions)
- the files `~/.netrc`, `~/.git-credentials`, `~/.npmrc`, `~/.pypirc`
- whatever the caller passes as `deny`
- the keychain: mach-lookup of `com.apple.securityd`, and reading or running
  `/usr/bin/security` (it can't be copied either, so a copy can't reuse Apple's signature)

With `writable=`: every write outside those roots, the temp roots (`/private/tmp`,
`/private/var/folders`, `$TMPDIR`), `/dev` and Codex's state files in `~/.codex` (sessions,
logs, sqlite, `auth.json` refresh). The `.git` and `.codex` directories inside a writable root
stay read-only. Codex's config, rules, hooks, skills, plugins and binaries stay unwritable, so a
run cannot plant code for the owner's next unsandboxed Codex.

## What stays readable

Everything else, including `~/.codex` (Codex needs `auth.json` to reach its model provider).

## Residual risk

- **Anything not on the list.** A token in `~/Documents`, a project `.env` or a shell history
  file is readable. The list covers the known credential stores; it doesn't cover everything.
- **Codex's own credentials.** `~/.codex/auth.json`, and any MCP OAuth tokens Codex keeps there,
  are readable by design.
- **The login keychain via `com.apple.SecurityServer`.** Denying that service broke Codex's TLS
  check, so it stays open. A keychain item whose ACL trusts a binary the run can execute (for
  example, an interpreter granted "Always Allow") is still reachable. Items that trust only
  `/usr/bin/security` are closed.
- **Model traffic.** Network stays on, and Codex sends the prompt and every file it reads to its
  model provider. The profile limits what it can read, not where that goes.
- **Hard links** made before the run, to a credential from a path that isn't denied.
- **Linux** has no protection (`protected=False`).
- **`co` commands inside the run** that need `keys.env` fail. That's the intent for runs on
  untrusted prompts. Pass `allow_co` only for folders that hold no keys.
