---
name: install-connectonion
description: Install and fully set up ConnectOnion on Windows, macOS, or Linux so EVERY `co` command works — find Python, pip install, `co init` (scaffolds the project AND authenticates, writing keys.env), confirm the account with `co status`, install a browser for `co browser`, then hand the user a plain-language summary. Use when the user says "install connectonion", "set up connectonion", "get me started with co", or a co command fails because nothing is configured yet.
tools:
  - Bash(python *)
  - Bash(python3 *)
  - Bash(py *)
  - Bash(pip *)
  - Bash(pip3 *)
  - Bash(co *)
  - Bash(patchright *)
  - shell
  - read_file
  - write
  - edit
---

# Install ConnectOnion Skill

Take a machine from nothing to a setup where **every `co` command works** — `co status`,
`co email`, `co browser`, the `co/*` models, all of it — on whatever OS the person uses.
Then tell them, in plain words, exactly what they have.

**Assume the person running this may not be technical.** They may not know what a "virtual
environment", "PATH", or "API key" is — that's fine. Do the technical work *for* them and
keep them informed in friendly, jargon-free language. Never dump a raw stack trace; turn
every problem into "here's what happened and here's what I'm doing about it."

## How to run this skill

1. **Work on the user's real OS.** Windows, macOS, and Linux differ in command names and
   shells — do Step 0 first and use the right ones. Don't assume `python3`, `grep`, or the
   `bash` tool exist everywhere.
2. **Verify every step before moving on** — each has a check; run it.
3. **Auto-correct instead of giving up.** On failure, don't paste the error — diagnose,
   apply the *Recovery* fix, retry (up to 2 attempts) before escalating.
4. **Only ask the human for things only a human can do** — installing Python, adding
   credit, an OAuth browser login. One plain sentence.
5. **Never print or store secrets** — confirm a key is *present*, never show its value.

## Step 0: Know the machine

Resolve the platform and the Python command. **Everything below writes `PY` for "the
Python that works here"** — resolve it once, reuse it.

- **Detect the OS** (e.g. `uname` prints `Darwin`/`Linux`; failing/absent → Windows).
- **Find Python (needs 3.10+).** Try in order, keep the first that prints 3.10+ — that's `PY`:
  ```bash
  python3 --version      # macOS / Linux usually
  python --version       # Windows usually
  py -3 --version        # Windows Python launcher
  ```
- **Pick the shell.** macOS/Linux: the `bash` tool is fine. **Windows: the `bash` tool does
  not work** (Unix-only) — use the `shell` tool and avoid `grep`/`cat`/`ls`. Prefer `co …`
  and `PY -c "…"`, which behave the same everywhere.

> **Recovery — Python missing or < 3.10** (give the path for *their* OS, don't install it yourself):
> - **Windows:** python.org installer (tick "Add python.exe to PATH") or `winget install Python.Python.3.12`; then `py -3` works.
> - **macOS:** python.org installer or `brew install python@3.12`.
> - **Linux:** `sudo apt install python3 python3-venv python3-pip` (or the distro equivalent).

## Step 1: Isolate with a virtual environment (recommended)

Keeps the install tidy and avoids "externally-managed-environment" errors:

```bash
# macOS / Linux
PY -m venv .venv && source .venv/bin/activate
# Windows PowerShell
py -3 -m venv .venv ; .venv\Scripts\Activate.ps1
# Windows cmd
py -3 -m venv .venv & .venv\Scripts\activate.bat
```

After activating, `python`/`pip` point inside `.venv` — `PY` can just be `python`. If venv
creation fails, it's optional: continue globally and note it to the user.

## Step 2: Install the package

Use `PY -m pip` (works even when a bare `pip` isn't on PATH):

```bash
PY -m pip install connectonion       # add -U to upgrade
co --version                          # confirm the CLI is on PATH
```

> **Recovery**
> - `co: command not found` after a good install → scripts folder not on PATH. Confirm with
>   `PY -m connectonion.cli.main --version`; then either use `PY -m connectonion.cli.main …`
>   or reinstall via `pipx install connectonion`.
> - "externally-managed-environment" / permission error → go back to Step 1's venv, retry.

## Step 3: Initialize the project — this also sets up keys.env

This is the core step. **`co init` does two things at once**: it scaffolds the project
(`agent.py`, `.env`, `.co/`) **and authenticates**, writing the account credentials to the
global `~/.co/keys.env` and copying them into the project `.env`. **Always pass `--yes`** so
it doesn't stop on a prompt:

```bash
co init --yes                     # existing folder: config + auth
# or start a fresh project folder (also authenticates):
co create my-agent --yes          # then: cd my-agent
```

Templates for `co create`: `minimal` (default), `coder`, `browser`, `web-research`,
`hosted-browser`, `co-ai`. Use `--template <name>`.

After this succeeds, `~/.co/keys.env` (and the project `.env`) contain:

```
OPENONION_API_KEY=<token>              # unlocks co/* models, co status, co email
AGENT_EMAIL=0x…@mail.openonion.ai      # the agent's own mailbox
IS_EMAIL_ACTIVE=true                   # co email is live
AGENT_ADDRESS=0x…                      # the agent's identity (public)
```

(The signing private key lives in `~/.co/keys/agent.key`, **not** in keys.env — never touch
or print it.)

> **Recovery — this is where `co auth` comes in**
> - `co init` printed an auth/network error, or the token didn't land (Step 4's `co status`
>   says "No API key found") → the scaffold worked but authentication didn't. Complete it:
>   ```bash
>   co auth        # re-runs just the authentication, writes OPENONION_API_KEY + AGENT_EMAIL
>   ```
>   `co auth` is safe to re-run any time; it refreshes the token in place.
> - "Directory not empty" → add `--force` only after the person confirms it's safe here.
> - Command hangs → you forgot `--yes`; re-run with it.

## Step 4: Confirm the account is wired up

Prove keys.env is good — `co status` needs `OPENONION_API_KEY` + the signing key + the
backend, so a clean result means everything downstream (models, email) will work:

```bash
co status        # shows agent email, balance, and free credit
co doctor        # cross-platform health check; "API Key" line should be ✓
```

**Optional — own provider keys instead of managed:** if the person would rather use their
own OpenAI/Anthropic/Google account, add the key to the project `.env` with the
`write`/`edit` tool (never echo it back): `OPENAI_API_KEY=…` (`gpt-*`),
`ANTHROPIC_API_KEY=…` (`claude-*`), `GEMINI_API_KEY=…` (`gemini-*`). Managed `co/*` still
needs `OPENONION_API_KEY` from Step 3.

> **Recovery**
> - "No API key found" → auth didn't land in Step 3. Run `co auth`, then re-check.
> - `co status` 401 / token expired → `co auth` again.

## Step 5: Browser — do this so `co browser` works (only if they need it)

Skip unless the person wants web automation (`co browser`, or the `browser`/`hosted-browser`
template). Two things to know first:

- **`pip install connectonion` installs the browser *library* (`patchright`) but NOT a
  browser to drive** — without one, `co browser` fails at launch with *"Chrome failed to
  start — full log at ~/.co/browser.log"*.
- **`co browser` runs a Unix-socket daemon, so it works on macOS/Linux but NOT on native
  Windows.** On Windows, do the browser work inside **WSL** (a Linux environment) and run
  these steps there. If the person is on native Windows and wants browser automation, tell
  them plainly: "browser control runs under WSL — want me to set that up?" and don't pretend
  `co browser` works in plain PowerShell.

Get a browser. The agent uses desktop **Google Chrome** if it's installed at the standard
OS path; otherwise install Patchright's browser (the deterministic option that always works):

```bash
PY -m patchright install chrome          # macOS / Linux (or WSL)
# Linux/CI without desktop libraries may need system deps (asks for sudo):
PY -m patchright install --with-deps chrome
```

**Verify it actually launches — `co doctor` is NOT enough here.** `co doctor` only checks
the patchright library/stealth driver; it shows `ok` even when no Chrome exists and the real
launch would fail. Prove the real thing by driving a page:

```bash
co browser go_to example.com     # navigates → Chrome launched OK. Then: co browser close
```

> **Recovery**
> - *"Chrome failed to start … ~/.co/browser.log"* → no drivable browser. Run
>   `PY -m patchright install chrome` (Linux: add `--with-deps`), or install desktop Google
>   Chrome to the standard path. Note: a Chrome in a non-standard spot (Windows per-user
>   `%LOCALAPPDATA%`, Linux snap/flatpak) isn't auto-detected — use `patchright install chrome`.
> - `co doctor` Browser line **missing** → patchright library gone: `PY -m pip install patchright`.
> - `co doctor` Browser line **broken** (stealth driver) → `PY -m pip install --force-reinstall --no-cache-dir patchright`.
> - `co browser do "…"` says *"requires authentication"* → the natural-language mode uses a
>   managed model; run `co auth` (Step 3 covers this). Direct verbs like `go_to` don't need it.

## Step 6: Optional integrations (Gmail / Outlook / Calendar)

Only if they want the agent to use their *personal* Gmail or Outlook. These are **separate**
from the built-in `co email` mailbox and require `OPENONION_API_KEY` first (Step 3):

```bash
co auth google       # Gmail Send + Google Calendar (browser OAuth)
co auth microsoft    # Outlook + Microsoft Calendar (browser OAuth)
```

Each opens a browser login — hand off: *"finish the login in the window that opened."*
Tokens are saved to `.env` / `~/.co/keys.env`. `co email` does **not** need these.

## Step 7: Verify the commands actually run

Confirm the things the person will use — not just that files exist. Run what's relevant:

```bash
co status                                          # account reachable
co email inbox --last 5                            # built-in mailbox responds (needs Step 3)
PY -c "from connectonion import Agent; print(Agent('smoke', max_iterations=2).input('Reply with exactly: OK'))"
co browser go_to example.com && co browser close   # only if Step 5 done — proves Chrome launches
```

> **Recovery — read the error and act**
> - `InsufficientCreditsError` (smoke run) → managed account out of credit; a *money* thing
>   only the person fixes. Show address/balance from `co status`, point to top up
>   (https://o.openonion.ai/purchase) or Discord (https://discord.gg/4xfD9k8AUF).
> - `co email` "No API key" / "AGENT_EMAIL not found" → auth didn't complete; run `co auth`.
> - `ModuleNotFoundError: connectonion` → wrong Python/venv active; re-activate Step 1's venv.

## Step 8: Hand the user a plain-language summary

The payoff. Run `co status`, then translate it — **don't paste the raw panel**:

| `co status` field | Say it like this |
|--------------------|------------------|
| Credits            | 🎁 **Free credit from ConnectOnion** — money they gave you to start |
| Balance            | 💰 **Money available right now** to run your agent |
| Email              | 📧 **Your agent's own email address** (send/receive with `co email`) |
| Agent Address/ID   | your agent's unique identity |

```
✅ You're all set up! Here's your ConnectOnion account:

  🎁  Free credit ConnectOnion gave you:  $X.XX
  💰  Money available to use now:          $X.XX
  📧  Your agent's email address:          you@mail.openonion.ai
  🤖  Model access:                        managed (co/* models) — nothing else needed
  🌐  Browser (co browser):                ready   (or "not set up"; on Windows: "runs under WSL")
  📦  Installed:                           connectonion vX.Y.Z  (Python 3.12 on Windows)
  📁  Your project:                        ./my-agent  (minimal template)

  What you can do now:
    • co status                      — check your balance any time
    • co email                       — read your agent's inbox
    • co email send <to> <sub> <msg> — send mail from your agent
    • co browser do "…"              — drive a web browser  (if set up)
    • python agent.py                — run your agent

  If the balance ever runs low, add more at https://o.openonion.ai/purchase —
  the free credit is enough to get going.
```

Adjust: **balance $0/low** → say it gently with the top-up link, no alarm. **Path B (own
keys)** → swap the money lines for "your own <provider> key", skip balance. **No browser** →
say it's not set up and offer. Keep it to the lines that matter to *this* person.

## Notes

- **`co init` / `co create` already authenticate** — you don't normally need a separate
  `co auth`; it's the repair step when init's auth didn't land (e.g. offline).
- **`co email` is the built-in managed mailbox** (`…@mail.openonion.ai`), activated by
  authentication (Step 3). It needs only `OPENONION_API_KEY` — *not* `co auth google`.
- **Cross-platform gotchas:** the `bash` *tool* is Unix-only (use `shell` on Windows);
  `python3` may be `python`/`py -3`; the browser binary is never auto-installed; and
  **`co browser` needs macOS/Linux (or WSL on Windows)** — its daemon uses Unix sockets.
- **`co doctor` does not confirm the browser can launch** — it only checks the patchright
  library/stealth driver. The real proof is `co browser go_to example.com`.
- `--yes` on `co init`/`co create` is mandatory for unattended runs.
- Never print, log, or commit keys; templates gitignore `.env` — keep it that way.
- State lives in `~/.co/` (global identity + keys.env) and the project's `.co/` + `.env`.
  Deleting one project never breaks another.
