---
name: install-connectonion
description: Install ConnectOnion and configure everything on Windows, macOS, or Linux — find Python, install the package, scaffold a project, set up API keys (managed or own), install a browser if needed — then verify with a real run and hand the user a plain-language account summary. Use when the user says "install connectonion", "set up connectonion", "get me started with co", or a co command fails because nothing is configured yet.
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

Take a machine from nothing to a working, configured agent — on **whatever operating
system the person is using** — then tell them, in plain words, exactly what they have.

**Assume the person running this may not be technical.** They may not know what a
"virtual environment", a "PATH", or an "API key" is, and that's fine — your job is to do
the technical work *for* them and keep them informed in friendly, jargon-free language.
Never dump a raw stack trace at them; translate every problem into "here's what happened
and here's what I'm doing about it."

## How to run this skill

1. **Work on the user's real OS.** Windows, macOS, and Linux differ in command names and
   shells. Do Step 0 first and use the right commands for that platform — don't assume
   `python3`, `grep`, or `bash` exist everywhere.
2. **Verify every step before moving on.** Never assume a command worked — check its
   output. Each step has a check; run it.
3. **Auto-correct instead of giving up.** When a step fails, do NOT stop and paste the
   error. Diagnose the cause, apply the known fix (the *Recovery* box under each step),
   and retry. Give each fix **up to 2 attempts** before escalating.
4. **Only ask the human for things only a human can do** — logging in through a browser,
   adding money, choosing a project name. Ask in one plain sentence.
5. **Keep them in the loop.** A short friendly line before each phase ("Installing now —
   about 30 seconds…") beats silence.
6. **Never print or store secrets.** Confirm a key is *present*, never show its value.

## Step 0: Know the machine

Figure out the platform and which commands to use. **Everything below writes `PY` for
"the Python command that works on this machine"** — resolve it once here, then reuse it.

- **Detect the OS.** If you have a shell, `uname` (prints `Darwin`/`Linux`) vs. failing =
  Windows is a quick tell; otherwise use whatever platform signal you have.
- **Find Python (needs 3.10+).** Try these in order and keep the first that prints 3.10 or
  newer — that is `PY`:

  ```bash
  python3 --version      # macOS / Linux usually
  python --version       # Windows usually, sometimes macOS/Linux
  py -3 --version        # Windows Python launcher
  ```

- **Pick the right shell.** On macOS/Linux the `bash` tool is fine. **On Windows the
  `bash` tool does not work** (it's Unix-only and returns an error) — use the
  cross-platform `shell` tool instead, and don't rely on `grep`/`cat`/`ls`. Prefer
  `co …` commands and `PY -c "…"` snippets, which behave the same everywhere.

> **Recovery**
> - None of `python3` / `python` / `py -3` is found, or all are < 3.10 → Python isn't
>   installed (or is too old). Tell the person plainly and give the path for *their* OS:
>   - **Windows:** install from python.org (tick "Add python.exe to PATH"), or
>     `winget install Python.Python.3.12`. Afterward `py -3` works.
>   - **macOS:** install from python.org, or `brew install python@3.12`.
>   - **Linux:** use the distro package manager (e.g. `sudo apt install python3 python3-venv python3-pip`).
>   Don't install system Python yourself unless they ask.

## Step 1: Isolate with a virtual environment (recommended)

Keeps this install tidy and avoids "externally-managed-environment" errors:

```bash
# macOS / Linux
PY -m venv .venv && source .venv/bin/activate

# Windows (PowerShell)
py -3 -m venv .venv ; .venv\Scripts\Activate.ps1
# Windows (cmd)
py -3 -m venv .venv & .venv\Scripts\activate.bat
```

After activating, `python`/`pip` point inside `.venv` — from here `PY` can just be
`python`. If venv creation fails, it's optional: skip it, continue globally, and note
that to the user.

## Step 2: Install the package

Use `PY -m pip` (works even when a bare `pip` isn't on PATH):

```bash
PY -m pip install connectonion       # add -U to upgrade an existing install
```

Verify before continuing:

```bash
co --version    # prints the installed version
co doctor       # cross-platform health check: Python, config, keys, browser
```

> **Recovery**
> - `co: command not found` after a successful install → the scripts folder isn't on
>   PATH. Confirm the package works with `PY -m connectonion.cli.main --version`; if that
>   prints a version, either use `PY -m connectonion.cli.main …` for the rest, or reinstall
>   with `pipx install connectonion` (which puts `co` on PATH).
> - "externally-managed-environment" / permission error → go back to Step 1 and use the
>   venv (exactly what it prevents), then retry.

## Step 3: Create or initialize a project

A project is just a folder with a `.env` (its keys) and a `.co/` folder (its config +
identity). The CLI is cross-platform here — the same commands work on every OS.

**New project** — **always pass `--yes`** so it doesn't stop to ask questions:

```bash
co create my-agent --yes                            # minimal (default)
co create my-coder --template coder --yes           # bash + file editing
co create my-bot --template browser --yes           # browser automation (see Step 6)
co create my-researcher --template web-research --yes
```

Other templates: `hosted-browser`, `co-ai`, `custom` (with `--description "..."`).

**Existing directory** — add config in place: `co init --yes` (config only) or
`co init --template minimal --yes` (full starter). The first run on a machine also
creates the global `~/.co/` config (keypair, agent address, agent email) automatically.

Confirm it worked with a cross-platform check (don't use `ls` — it's not on Windows):

```bash
co doctor       # its Config/Keys lines show ✓ when .co/ and keys exist
# or, portably:
PY -c "import os; print('OK' if os.path.exists('.env') and os.path.isdir('.co') else 'MISSING')"
```

> **Recovery**
> - "Directory not empty" warning → the folder already has files. Add `--force` only after
>   the person confirms it's safe to write here.
> - The command hangs → it's waiting on an interactive prompt; you forgot `--yes`. Re-run
>   with `--yes`.
> - `.env` / `.co/` missing afterward → re-run and read the output before continuing.

## Step 4: Configure model access (pick ONE path)

An agent can't think without a model. Two paths — pick by what the person has.

**Path A — managed keys (recommended; no provider account, comes with free credit):**

```bash
co auth
```

Logs them in and saves `OPENONION_API_KEY` to `~/.co/keys.env` (and the project `.env`).
Agents then use `co/*` models — `co/o4-mini`, `co/gpt-4o`, `co/claude-sonnet-4-5`,
`co/gemini-2.5-pro` — with nothing else to configure. `co auth` opens a browser login, so
hand off: *"Please finish the login in the browser window that opened — I'll continue
once you're back."*

**Path B — their own provider key:** add it to the project `.env` with the `write`/`edit`
tool (never echo the value back afterward):

```
OPENAI_API_KEY=sk-...        # for gpt-* models
ANTHROPIC_API_KEY=sk-ant-... # for claude-* models
GEMINI_API_KEY=...           # for gemini-* models
```

Model name picks the provider: `gpt-*` → OpenAI, `claude-*` → Anthropic, `gemini-*` →
Google, `co/*` → managed keys.

Verify (cross-platform — `co doctor` reports where it found the key, no `grep` needed):

```bash
co status       # Path A: shows account, balance, and free credit
co doctor       # either path: the "API Key" line shows ✓ Found in .env / keys.env
```

> **Recovery**
> - `co auth` login didn't complete → safe to re-run; it refreshes the token in place.
> - "No API key found" → the key didn't land. Re-run `co auth` (Path A) or re-check the
>   variable name spelling in `.env` (Path B).

## Step 5: Verify with a real run

Prove the whole chain works with a tiny 2-line agent. **Match the model to the path from
Step 4** — the default model is a managed `co/*` one, so a Path-B setup must name its own
provider's model:

```bash
# Path A (managed keys — default model):
PY -c "from connectonion import Agent; print(Agent('smoke-test', max_iterations=2).input('Reply with exactly: OK'))"

# Path B (own key — name a model your key serves, e.g. OpenAI):
PY -c "from connectonion import Agent; print(Agent('smoke-test', model='gpt-4o-mini', max_iterations=2).input('Reply with exactly: OK'))"
```

Expected: a reply containing `OK`.

> **Recovery — read the error and act, don't just report it**
> - `InsufficientCreditsError` → the managed account is out of credit. A *money* thing only
>   the person can fix: show the address and balance from `co status`, point them to top up
>   (https://o.openonion.ai/purchase) or Discord (https://discord.gg/4xfD9k8AUF). Not an
>   install failure.
> - Auth / `401` → the key from Step 4 didn't land. Re-run `co auth` (A) or fix `.env` (B),
>   then retry once.
> - `ModuleNotFoundError: connectonion` → wrong Python/venv is active. Re-activate the venv
>   from Step 1 and retry.

## Step 6: Browser setup — ONLY if they need web automation

Skip this entirely unless the person chose the `browser` / `hosted-browser` template or
wants the agent to drive a web browser. **This is a real gotcha:** `pip install
connectonion` installs the browser *library* (`patchright`) but **NOT a browser to
drive**. Without one, browser commands fail.

The agent looks for a **real Google Chrome** first (auto-detected on Windows, macOS, and
Linux). If Chrome isn't installed, install Patchright's own browser:

```bash
PY -m patchright install chrome    # downloads a Chromium the agent can drive
```

Verify:

```bash
co doctor       # the Browser line reports ok / broken / missing
```

> **Recovery**
> - `co doctor` browser line says **missing** → run `PY -m patchright install chrome`.
> - Says **broken** (stealth driver) → `PY -m pip install --force-reinstall --no-cache-dir patchright`, then re-run `patchright install chrome`.
> - Still failing → check `~/.co/browser.log`; the person may simply install desktop Google
>   Chrome, which the agent will pick up automatically.

## Step 7: Hand the user a plain-language summary

The payoff. Run `co status` and turn it into a short, friendly summary — **don't paste the
raw panel**, translate it.

```bash
co status
```

Map the `co status` fields to plain language:

| `co status` field | Say it like this |
|--------------------|------------------|
| Credits            | 🎁 **Free credit from ConnectOnion** — money they gave you to start |
| Balance            | 💰 **Money available right now** to run your agent |
| Total Spent        | what's been used so far |
| Email              | 📧 **Your agent's own email address** (it can send/receive mail) |
| Agent ID / Address | your agent's unique ID |

Then present something like this (fill in the real values):

```
✅ You're all set up! Here's your ConnectOnion account:

  🎁  Free credit ConnectOnion gave you:  $X.XX
  💰  Money available to use now:          $X.XX
  📧  Your agent's email address:          you@mail.openonion.ai
  🤖  Model access:                        managed (co/* models) — nothing else needed
  📦  Installed:                           connectonion vX.Y.Z  (Python 3.12 on Windows)
  📁  Your project:                        ./my-agent  (minimal template)

  You can start using your agent now. If the balance ever runs low, you can add
  more at https://o.openonion.ai/purchase — the free credit is enough to get going.
```

Adjust for the situation:
- **Balance $0 / low** → say it gently: "Your free credit is used up, so you'll need to add
  a little to keep running the agent — here's where: …". No alarm, no jargon.
- **Path B (own keys)** → replace the money lines with "Model access: your own <provider>
  key"; skip balance (their provider bills them directly).
- **Browser installed** → add "🌐 Browser: ready".
- **Integrations connected** → add "📬 Connected: Gmail" etc.

Keep it to the handful of lines that matter to *this* person. Warmth over completeness.

## Notes

- **Cross-platform:** the `co` CLI runs on Windows, macOS, and Linux. The gotchas are (1)
  the `bash` *tool* is Unix-only — use `shell` on Windows; (2) `python3` may be `python`
  or `py -3` on Windows (that's why Step 0 resolves `PY`); (3) the browser binary is never
  auto-installed (Step 6).
- `--yes` on `co create` / `co init` is mandatory for unattended runs, or the command
  blocks on prompts.
- Never print, log, or commit API keys. Templates gitignore `.env` — keep it that way.
- `co auth` is safe to re-run; it refreshes the token in place.
- A failing smoke test with a green `co doctor` / `co status` is a model-or-credit issue,
  not an install issue — say so plainly.
- All state lives in `~/.co/` (global identity + keys) and the project's `.co/` + `.env`.
  Deleting one project never breaks another.
