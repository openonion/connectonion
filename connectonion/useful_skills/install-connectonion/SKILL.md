---
name: install-connectonion
description: Install ConnectOnion and configure everything — Python check, package, project scaffold, API keys (managed or own), optional Google/Microsoft integrations — then verify with a real run and hand the user a plain-language account summary. Use when the user says "install connectonion", "set up connectonion", "get me started with co", or a co command fails because nothing is configured yet.
tools:
  - Bash(pip *)
  - Bash(pip3 *)
  - Bash(python *)
  - Bash(python3 *)
  - Bash(co *)
  - Bash(cat *)
  - Bash(ls *)
  - Bash(grep *)
  - read_file
  - write
  - edit
---

# Install ConnectOnion Skill

Take a machine from nothing to a working, configured agent — then tell the person,
in plain words, exactly what they have.

**Assume the person running this may not be technical.** They may not know what a
"virtual environment", a "PATH", or an "API key" is, and that's fine — your job is
to do the technical work *for* them and keep them informed in friendly, jargon-free
language. Never dump a raw stack trace at them; translate every problem into "here's
what happened and here's what I'm doing about it."

## How to run this skill

1. **Verify every step before moving on.** Never assume a command worked — check its
   output. Each step below has a check; run it.
2. **Auto-correct instead of giving up.** When a step fails, do NOT stop and paste the
   error. Diagnose the cause, apply the known fix (see the *Recovery* box under each
   step and the reference table at the end), and retry. Give each fix **up to 2
   attempts** before escalating.
3. **Only ask the human for things only a human can do** — logging in through a browser,
   adding money, choosing a project name. Ask in one plain sentence, never with a wall
   of options.
4. **Keep them in the loop.** A short friendly line before each phase ("Installing the
   software now — about 30 seconds…") is worth more than silence.
5. **Never print or store secrets.** Confirm a key is *present*, never show its value.

## Step 1: Check Python

ConnectOnion needs **Python 3.10 or newer**. Check first — everything else depends on it.

```bash
python3 --version        # must be 3.10+
python3 -m pip --version
```

A virtual environment keeps this install tidy and isolated (recommended, especially on
a shared or fresh machine):

```bash
python3 -m venv .venv
source .venv/bin/activate      # Windows: .venv\Scripts\activate
```

After activating, `python` and `pip` point inside `.venv` — use them for the rest.

> **Recovery**
> - `python3: command not found` or version < 3.10 → tell the person in plain words:
>   "This needs Python 3.10 or newer and I couldn't find it. You'll need to install it
>   from python.org (or your app store) first." Don't try to install system Python
>   yourself unless they ask.
> - `venv` creation fails → skip the venv (it's optional) and continue; note it so they
>   know the install is global.

## Step 2: Install the package

```bash
pip install connectonion        # or: pip install -U connectonion to upgrade
```

Verify before continuing:

```bash
co --version    # prints the installed version
co doctor       # diagnoses the installation
```

> **Recovery**
> - `co: command not found` after a successful install → the scripts folder isn't on
>   PATH. Confirm the package itself works with
>   `python -m connectonion.cli.main --version`; if that prints a version, either use
>   `python -m connectonion.cli.main …` for the rest, or reinstall with
>   `pipx install connectonion` (which puts `co` on PATH). Retry the check.
> - `pip: command not found` → use `python3 -m pip install connectonion`.
> - Permission / "externally-managed-environment" error → go back and use the venv from
>   Step 1 (this is exactly what it prevents), then retry.

## Step 3: Create or initialize a project

A project is just a folder with a `.env` (its keys) and a `.co/` folder (its config +
identity). Pick based on what the person wants:

**New project** — **always pass `--yes`** so it doesn't stop to ask questions:

```bash
co create my-agent --yes                            # minimal (default)
co create my-coder --template coder --yes           # bash + file editing
co create my-bot --template browser --yes           # browser automation
co create my-researcher --template web-research --yes
```

Other templates: `hosted-browser`, `co-ai`, `custom` (with `--description "..."`).

**Existing directory** — add config in place:

```bash
co init --yes                     # adds the .co/ folder only
co init --template minimal --yes  # adds the full starter template
```

The very first run on a machine also creates the global `~/.co/` config (a keypair, the
agent's address, and its email) automatically — no separate step. Confirm the project
was created:

```bash
ls -la .env .co/          # both should exist
```

> **Recovery**
> - "Directory not empty" warning → the folder already has files. Only add `--force`
>   after confirming with the person that it's safe to write into this folder.
> - The command hangs → it's waiting on an interactive prompt; you forgot `--yes`.
>   Re-run with `--yes`.
> - `.env` or `.co/` missing afterward → re-run the command and read its output; don't
>   proceed to Step 4 until both exist.

## Step 4: Configure model access (pick ONE path)

An agent can't think without a model. Two paths — pick by what the person has.

**Path A — managed keys (recommended; no provider account, comes with free credit):**

```bash
co auth
```

This logs them in and saves `OPENONION_API_KEY` to `~/.co/keys.env` (and the project
`.env`). Agents then use `co/*` models — `co/o4-mini`, `co/gpt-4o`,
`co/claude-sonnet-4-5`, `co/gemini-2.5-pro` — with nothing else to configure.
`co auth` opens a browser login, so this is a good moment to hand off: *"Please finish
the login in the browser window that opened — I'll continue once you're back."*

**Path B — their own provider key:** put it in the project `.env`:

```
OPENAI_API_KEY=sk-...        # for gpt-* models
ANTHROPIC_API_KEY=sk-ant-... # for claude-* models
GEMINI_API_KEY=...           # for gemini-* models
```

The model name picks the provider: `gpt-*` → OpenAI, `claude-*` → Anthropic,
`gemini-*` → Google, `co/*` → managed keys. Use the `write`/`edit` tool to add the key
to `.env` — never echo the key back afterward.

Verify whichever path you chose:

```bash
co status                # Path A: shows the account, balance, and free credit
grep -c "API_KEY" .env   # Path B: confirms the key landed in .env (count > 0)
```

> **Recovery**
> - `co auth` browser login didn't complete → it's safe to re-run; `co auth` just
>   refreshes the token in place.
> - `co status` says "No API key found" → the login didn't save. Re-run `co auth`
>   (Path A) or re-check the spelling of the variable name in `.env` (Path B).

## Step 5: Verify with a real run

Prove the whole chain works with a tiny 2-line agent. **Match the model to the path from
Step 4** — the default model is a managed `co/*` one, so a Path-B setup must name its own
provider's model:

```bash
# Path A (managed keys — default model):
python -c "
from connectonion import Agent
print(Agent('smoke-test', max_iterations=2).input('Reply with exactly: OK'))
"

# Path B (own key — name a model your key serves, e.g. OpenAI):
python -c "
from connectonion import Agent
print(Agent('smoke-test', model='gpt-4o-mini', max_iterations=2).input('Reply with exactly: OK'))
"
```

Expected: a reply containing `OK`.

> **Recovery — read the error and act, don't just report it**
> - `InsufficientCreditsError` → the managed account is out of credit. This is a
>   *money* thing only the person can fix: show them the account address and balance
>   from `co status`, and point them to top up (https://o.openonion.ai/purchase) or ask
>   in Discord (https://discord.gg/4xfD9k8AUF). Not an install failure.
> - Auth / `401` errors → the key from Step 4 didn't land. Re-run `co auth` (Path A) or
>   fix `.env` (Path B), then retry the run once.
> - `ModuleNotFoundError: connectonion` → wrong Python/venv is active. Re-activate the
>   venv from Step 1 and retry.
> - `co doctor` re-diagnoses the installation at any point if you're unsure what broke.

## Step 6: Hand the user a plain-language summary

This is the payoff. Run `co status` one more time and turn its output into a short,
friendly summary the person actually understands. **Do not just paste the raw panel** —
translate it.

```bash
co status
```

`co status` reports these fields — map them to plain language:

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
  📦  Installed:                           connectonion vX.Y.Z
  📁  Your project:                        ./my-agent  (minimal template)

  You can start using your agent now. If the balance ever runs low, you can
  add more at https://o.openonion.ai/purchase — but the free credit is enough
  to get going.
```

Adjust for the situation:
- **Balance is $0 / low** → say it gently and factually: "Your free credit is used up, so
  you'll need to add a little to run the agent — here's where: …". No alarm, no jargon.
- **Path B (own keys)** → replace the money lines with "Model access: your own <provider>
  key" and skip balance (their provider bills them directly).
- **Integrations connected** → add a line: "📬 Connected: Gmail" etc.

Keep it to the handful of lines that matter to *this* person. Warmth over completeness.

## Notes

- `--yes` on `co create` / `co init` is mandatory for unattended runs; without it the
  command blocks on interactive prompts.
- Never print, log, or commit API keys. The templates gitignore `.env` — keep it that way.
- `co auth` is safe to re-run; it refreshes the token in place.
- A failing smoke test with a green `co doctor` / `co status` is a model-or-credit issue,
  not an install issue — say so plainly.
- All state lives in two places: `~/.co/` (global identity + keys) and the project's
  `.co/` + `.env` (per-project). Deleting one project never breaks another.
