# install-connectonion

Install and fully set up ConnectOnion so **every `co` command works** — `co status`,
`co email`, `co browser`, the `co/*` models — on Windows, macOS, or Linux. Built to be run
**for a possibly non-technical person**: it does the technical work for them, auto-corrects
failures instead of dumping errors, and ends with a plain-language account summary.

## Install

```bash
co copy install-connectonion
# → .co/skills/install-connectonion/SKILL.md
```

(Chicken-and-egg note: this skill is for agents that set up ConnectOnion on *other*
machines/projects — a coding agent that already has `co` can copy it, then walk a fresh
environment through the whole setup.)

## Usage

```
/install-connectonion
```

The skill walks these steps, each verified before the next, and self-corrects on failure:

0. **Know the machine** — detect the OS; resolve the Python command (`python3` / `python` /
   `py -3`, needs 3.10+) as `PY`; pick the shell (the `bash` tool is Unix-only → `shell` on Windows)
1. **Virtualenv** — isolate the install (also dodges "externally-managed-environment")
2. **Install** — `PY -m pip install connectonion`, verify `co --version`
3. **`co init --yes`** — scaffolds the project **and authenticates**, writing `keys.env`
   (`OPENONION_API_KEY`, `AGENT_EMAIL`, `IS_EMAIL_ACTIVE=true`). `co auth` is the repair step
   if that authentication didn't land (e.g. offline)
4. **Confirm** — `co status` / `co doctor` prove the account and keys are wired up
5. **Browser** (only if needed) — `pip` doesn't bring a browser; `patchright install chrome`
   (or system Chrome). `co browser` is macOS/Linux only (WSL on Windows)
6. **Integrations** (optional) — `co auth google` / `co auth microsoft` for personal Gmail/Outlook
7. **Verify the commands run** — `co status`, `co email`, a real agent run, a real browser nav
8. **Summary** — a friendly account report + the list of commands they can now use

## The key facts it gets right

Earlier drafts of this skill were wrong about the setup flow. The current version is
grounded in the actual CLI code:

- **`co init` (and `co create`) already authenticate** — they call `authenticate()`
  unconditionally, so after `co init --yes` the `keys.env` already holds
  `OPENONION_API_KEY` + `AGENT_EMAIL` + `IS_EMAIL_ACTIVE=true`. A separate `co auth` is the
  **repair** step (offline during init, expired token), not a required second command.
- **`co email` is the built-in managed mailbox** (`…@mail.openonion.ai`), activated by that
  authentication. It needs only `OPENONION_API_KEY` — **not** `co auth google`. Gmail/Outlook
  OAuth (`co auth google`/`microsoft`) is a separate, optional thing.
- **The browser binary is never auto-installed.** `pip install connectonion` brings the
  `patchright` library but no Chrome; `co browser` fails with *"Chrome failed to start"*
  until you run `patchright install chrome` or have desktop Chrome. And `co doctor` does
  **not** catch this — it only checks the patchright library, so the skill proves the
  browser with a real `co browser go_to example.com`.
- **`co browser` is POSIX-only** (Unix-socket daemon) — macOS/Linux, or WSL on Windows.

## Built for non-technical users, on any OS

- **Cross-platform.** Detects the OS, resolves `PY`, uses `shell` (not the Unix-only `bash`
  tool) on Windows, and leans on `co status` / `co doctor` for verification.
- **Auto-correction.** Every step has a *Recovery* block: diagnose → apply the known fix →
  retry (up to 2 attempts). Escalates to the human only for installing Python, adding
  credit, or an OAuth browser login.
- **A real end-of-run UI.** Step 8 turns `co status` into a warm summary and tells the person
  exactly which commands they can now run:

  ```
  ✅ You're all set up! Here's your ConnectOnion account:

    🎁  Free credit ConnectOnion gave you:  $X.XX
    💰  Money available to use now:          $X.XX
    📧  Your agent's email address:          you@mail.openonion.ai
    🤖  Model access:                        managed (co/* models)
    🌐  Browser (co browser):                ready
    📦  Installed:                           connectonion vX.Y.Z

    What you can do now: co status · co email · co browser do "…" · python agent.py
  ```

## See Also

- [Quickstart](../quickstart.md) — the human-facing version of the same flow
- [co auth](../cli/auth.md) — what authentication writes to keys.env
- [co email](../cli/email.md) — the built-in agent mailbox
- [co browser](../cli/browser.md) — browser prerequisites (patchright install chrome)
- [Built-in Skills](README.md) — all copyable skills
