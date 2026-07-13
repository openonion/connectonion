---
name: install-connectonion
description: Install ConnectOnion and configure everything — package, project scaffold, API keys (managed or own), optional Google/Microsoft integrations — then verify with a real agent run. Use when the user says "install connectonion", "set up connectonion", "get me started with co", or a co command fails because nothing is configured yet.
tools:
  - Bash(pip *)
  - Bash(pip3 *)
  - Bash(python *)
  - Bash(python3 *)
  - Bash(co *)
  - Bash(cat *)
  - Bash(grep *)
  - read_file
  - write
---

# Install ConnectOnion Skill

Take a machine from nothing to a working, configured agent. Every step verifies
itself before moving on — never assume a step worked.

## Step 1: Install the package

```bash
pip install connectonion        # or: pip install -U connectonion to upgrade
```

Verify before continuing:

```bash
co --version    # prints the installed version
co doctor       # diagnoses the installation
```

If `co` is not found after install, the scripts directory isn't on PATH — run
`python -m connectonion.cli.main --version` to confirm the package itself works,
then fix PATH (or use `pipx install connectonion`).

## Step 2: Create or initialize a project

New project — **always pass `--yes`** (skips interactive prompts that would hang
an unattended run) and pick the template that matches the goal:

```bash
co create my-agent --yes                            # minimal (default)
co create my-coder --template coder --yes           # bash + file editing
co create my-bot --template browser --yes           # browser automation
co create my-researcher --template web-research --yes
```

Other templates: `hosted-browser`, `co-ai`, `custom` (with `--description "..."`).

Existing directory:

```bash
co init --yes                     # adds .co/ folder only
co init --template minimal --yes  # adds the full template
```

First run ever on this machine also creates the global `~/.co/` config
(keypair, agent address, agent email) automatically — no separate step.

## Step 3: Configure model access (pick ONE path)

**Path A — managed keys (recommended, no provider account needed):**

```bash
co auth
```

This saves `OPENONION_API_KEY` to `~/.co/keys.env` (and the project `.env` if
present). Agents then use `co/*` models — `co/o4-mini`, `co/gpt-4o`,
`co/claude-sonnet-4-5`, `co/gemini-2.5-pro` — with no other keys.

**Path B — your own provider key:** put it in the project `.env`:

```
OPENAI_API_KEY=sk-...        # for gpt-* models
ANTHROPIC_API_KEY=sk-ant-... # for claude-* models
GEMINI_API_KEY=...           # for gemini-* models
```

The model prefix picks the provider: `gpt-*` → OpenAI, `claude-*` → Anthropic,
`gemini-*` → Google, `co/*` → managed keys.

Verify whichever path you chose:

```bash
co status       # account/balance for managed keys
grep -c "API_KEY" .env   # own keys: confirm the key landed in .env
```

## Step 4: Optional integrations

Only if the user needs email/calendar tools:

```bash
co auth google      # Gmail + Google Calendar (opens browser OAuth)
co auth microsoft   # Outlook + Microsoft Calendar
```

## Step 5: Verify with a real run

Prove the whole chain works — a 2-line agent, end to end. **Match the model to
the path chosen in Step 3** (the default model is a managed `co/*` one, so a
Path-B setup must name its own provider's model):

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

Expected: a reply containing `OK`. Anything else, read the error:

- `InsufficientCreditsError` — managed-key account needs credits: run
  `co status` for the address/balance, top up or join Discord
  (https://discord.gg/4xfD9k8AUF).
- Auth/401 errors — the key path from Step 3 didn't land: rerun `co auth`
  (Path A) or check `.env` spelling (Path B).
- `co doctor` re-diagnoses the installation at any point.

## Step 6: Report

Tell the user exactly what is now configured:

- installed version (`co --version` output)
- project path and template
- model access path (managed `co/*` or which provider keys)
- integrations connected (google/microsoft/none)
- the smoke-test reply

## Notes

- Never print or commit API keys — `.env` is gitignored by the templates; keep it that way.
- `co auth` is safe to re-run; it refreshes the token in place.
- All state lives in two places: `~/.co/` (global identity + keys) and the
  project's `.co/` + `.env` (per-project). Deleting a project never breaks
  another one.
